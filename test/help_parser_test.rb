require_relative "test_helper"
require "basecamp_mcp/help_parser"

class HelpParserTest < Minitest::Test
  def parse(name)
    BasecampMcp::HelpParser.parse(File.read(File.join(FIXTURES, "#{name}_help.txt")))
  end

  def test_todos_create_required_positional
    parsed = parse("todos_create")
    assert_includes parsed[:positional], { "name" => "content", "required" => true, "description" => "Content" }
  end

  def test_todos_create_string_flag
    parsed = parse("todos_create")
    due = parsed[:flags].find { |f| f["name"] == "due" }
    assert_equal "string", due["type"]
    assert_equal "d", due["short"]
  end

  def test_todos_create_string_array_flag
    parsed = parse("todos_create")
    attach = parsed[:flags].find { |f| f["name"] == "attach" }
    assert_equal "array", attach["type"]
  end

  def test_todos_create_excludes_help_flag
    parsed = parse("todos_create")
    refute parsed[:flags].any? { |f| f["name"] == "help" }
  end

  def test_cards_create_optional_positional
    parsed = parse("cards_create")
    title = parsed[:positional].find { |p| p["name"] == "title" }
    body  = parsed[:positional].find { |p| p["name"] == "body" }
    assert title["required"]
    refute body["required"]
  end

  def test_summary_extracted
    parsed = parse("projects_list")
    refute_empty parsed[:summary]
  end
end
