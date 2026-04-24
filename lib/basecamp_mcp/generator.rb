require "open3"
require "json"
require_relative "help_parser"

module BasecampMcp
  # Shells out to the basecamp CLI to enumerate commands and build a static
  # tool-schema file. Runs offline from `rake tools:generate`, not at server
  # startup.
  class Generator
    def initialize(basecamp_bin: ENV["BASECAMP_BIN"] || "basecamp")
      @basecamp_bin = basecamp_bin
    end

    def generate
      categories = list_commands
      tools = []

      categories.each do |category|
        next if category["name"] == "Shortcuts"

        Array(category["commands"]).each do |cmd|
          group       = cmd["name"]
          group_desc  = cmd["description"]
          Array(cmd["actions"]).each do |action|
            tools << tool_for(group, action, group_desc)
          end
        end
      end

      tools.sort_by { |t| t["name"] }
    end

    def tool_for(group, action, group_desc)
      help  = help_text(group, action)
      parsed = HelpParser.parse(help)

      {
        "name"         => "#{group}_#{action}",
        "group"        => group,
        "action"       => action,
        "description"  => parsed[:summary].empty? ? "#{action} #{group}" : parsed[:summary],
        "positional"   => parsed[:positional],
        "flags"        => parsed[:flags],
        "input_schema" => build_schema(parsed),
      }
    end

    def build_schema(parsed)
      properties = {}
      required = []

      parsed[:positional].each do |pos|
        properties[pos["name"]] = { "type" => "string", "description" => pos["description"] }
        required << pos["name"] if pos["required"]
      end

      parsed[:flags].each do |flag|
        properties[flag["name"]] = schema_for_flag(flag)
      end

      schema = { "type" => "object", "properties" => properties }
      schema["required"] = required unless required.empty?
      schema
    end

    def schema_for_flag(flag)
      case flag["type"]
      when "array"
        { "type" => "array", "items" => { "type" => "string" }, "description" => flag["description"] }
      when "integer"
        { "type" => "integer", "description" => flag["description"] }
      when "boolean"
        { "type" => "boolean", "description" => flag["description"] }
      else
        { "type" => "string", "description" => flag["description"] }
      end
    end

    def list_commands
      stdout, stderr, status = Open3.capture3(@basecamp_bin, "commands", "--json")
      raise "basecamp commands --json failed: #{stderr}" unless status.success?

      envelope = JSON.parse(stdout)
      envelope["data"]
    end

    def help_text(group, action)
      stdout, _stderr, _status = Open3.capture3(@basecamp_bin, group, action, "--help")
      stdout
    end
  end
end
