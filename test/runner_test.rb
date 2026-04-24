require_relative "test_helper"
require "basecamp_mcp/runner"

class RunnerTest < Minitest::Test
  def setup
    @spec = {
      "group"  => "todos",
      "action" => "create",
      "positional" => [
        { "name" => "content", "required" => true, "description" => "Content" },
      ],
      "flags" => [
        { "name" => "project", "type" => "string",  "description" => "Project" },
        { "name" => "attach",  "type" => "array",   "description" => "Attach" },
        { "name" => "verbose", "type" => "boolean", "description" => "Verbose" },
      ],
    }
    @runner = BasecampMcp::Runner.new
  end

  def test_build_argv_positional_and_flags
    argv = @runner.build_argv(@spec, {
      "content" => "Write docs",
      "project" => "123",
      "attach"  => ["a.png", "b.png"],
      "verbose" => true,
    })

    assert_equal [
      "todos", "create", "Write docs",
      "--project", "123",
      "--attach",  "a.png",
      "--attach",  "b.png",
      "--verbose",
      "--json",
    ], argv
  end

  def test_build_argv_omits_nil_flags
    argv = @runner.build_argv(@spec, { "content" => "x" })
    assert_equal ["todos", "create", "x", "--json"], argv
  end

  def test_build_argv_omits_false_boolean
    argv = @runner.build_argv(@spec, { "content" => "x", "verbose" => false })
    assert_equal ["todos", "create", "x", "--json"], argv
  end

  def test_build_argv_raises_on_missing_required
    assert_raises(ArgumentError) { @runner.build_argv(@spec, {}) }
  end

  def test_parse_envelope_valid_json
    assert_equal({ "ok" => true, "data" => [1, 2] }, @runner.parse_envelope('{"ok":true,"data":[1,2]}'))
  end

  def test_parse_envelope_invalid_returns_nil
    assert_nil @runner.parse_envelope("not json")
  end
end
