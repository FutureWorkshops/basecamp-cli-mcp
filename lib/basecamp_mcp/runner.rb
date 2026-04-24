require "open3"
require "json"

module BasecampMcp
  class BasecampError < StandardError
    attr_reader :stderr, :data

    def initialize(message, stderr: nil, data: nil)
      super(message)
      @stderr = stderr
      @data = data
    end
  end

  # Builds argv for a basecamp CLI invocation and runs it.
  class Runner
    def initialize(basecamp_bin: ENV["BASECAMP_BIN"] || "basecamp")
      @basecamp_bin = basecamp_bin
    end

    # tool_spec is an entry from data/tools.json — includes group, action, positional, flags.
    # params is the argument hash supplied to the MCP tool call.
    # Returns the parsed `data` field from the CLI's JSON envelope (or raw text fallback).
    def call(tool_spec, params)
      argv = build_argv(tool_spec, params || {})
      stdout, stderr, status = Open3.capture3(@basecamp_bin, *argv)

      payload = parse_envelope(stdout)

      if status.success? && (payload.nil? || payload["ok"] != false)
        payload ? payload["data"] : stdout
      else
        message =
          if payload && payload["error"]
            payload["error"].is_a?(Hash) ? (payload["error"]["message"] || payload["error"].to_json) : payload["error"].to_s
          else
            "basecamp CLI exited with status #{status.exitstatus}"
          end
        raise BasecampError.new(message, stderr: stderr, data: payload)
      end
    end

    def build_argv(tool_spec, params)
      argv = [tool_spec["group"], tool_spec["action"]]

      (tool_spec["positional"] || []).each do |pos|
        value = params[pos["name"]]
        if value.nil? || value.to_s.empty?
          next unless pos["required"]

          raise ArgumentError, "Missing required argument: #{pos["name"]}"
        end
        argv << value.to_s
      end

      (tool_spec["flags"] || []).each do |flag|
        value = params[flag["name"]]
        next if value.nil?

        case flag["type"]
        when "boolean"
          argv << "--#{flag["name"]}" if value
        when "array"
          Array(value).each do |v|
            argv << "--#{flag["name"]}" << v.to_s
          end
        else
          argv << "--#{flag["name"]}" << value.to_s
        end
      end

      argv << "--json"
      argv
    end

    def parse_envelope(stdout)
      JSON.parse(stdout)
    rescue JSON::ParserError
      nil
    end
  end
end
