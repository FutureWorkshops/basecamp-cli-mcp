require "mcp"
require "json"
require_relative "runner"

module BasecampMcp
  class Server
    TOOLS_FILE = File.expand_path("../../data/tools.json", __dir__)

    def initialize(tools_file: TOOLS_FILE, runner: Runner.new)
      @tools_file = tools_file
      @runner = runner
    end

    def build
      tool_specs = JSON.parse(File.read(@tools_file))
      tools = tool_specs.map { |spec| define_tool(spec) }

      MCP::Server.new(
        name: "basecamp",
        title: "Basecamp",
        version: BasecampMcp::VERSION,
        instructions: "Wraps the `basecamp` CLI. Each tool corresponds to a CLI action; all tools return the parsed JSON payload from the CLI.",
        tools: tools,
      )
    end

    def run
      transport = MCP::Server::Transports::StdioTransport.new(build)
      transport.open
    end

    private

    def define_tool(spec)
      runner = @runner
      MCP::Tool.define(
        name: spec["name"],
        description: spec["description"],
        input_schema: spec["input_schema"],
      ) do |server_context: nil, **params|
        string_params = params.each_with_object({}) { |(k, v), h| h[k.to_s] = v }
        begin
          data = runner.call(spec, string_params)
          text =
            if data.nil?
              ""
            elsif data.is_a?(String)
              data
            else
              JSON.pretty_generate(data)
            end
          MCP::Tool::Response.new([{ type: "text", text: text }])
        rescue BasecampError => e
          detail = e.stderr && !e.stderr.empty? ? "\n#{e.stderr}" : ""
          MCP::Tool::Response.new([{ type: "text", text: e.message + detail }], error: true)
        rescue ArgumentError => e
          MCP::Tool::Response.new([{ type: "text", text: e.message }], error: true)
        end
      end
    end
  end
end
