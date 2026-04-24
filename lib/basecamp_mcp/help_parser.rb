require "strscan"

module BasecampMcp
  # Parses `basecamp <group> <action> --help` output into a structured description
  # of positional arguments and flags. Used only by the generator — not on the
  # runtime hot path.
  module HelpParser
    module_function

    # Returns:
    #   {
    #     summary:    "Create a new todo in a project.",
    #     positional: [{name: "content", required: true, description: "Content"}, ...],
    #     flags:      [{name: "due", short: "d", type: "string", description: "..."}, ...],
    #   }
    def parse(help_text)
      {
        summary:    extract_summary(help_text),
        positional: extract_positional(help_text),
        flags:      extract_flags(help_text),
      }
    end

    def extract_summary(text)
      # First non-blank line(s) until USAGE.
      lines = []
      text.each_line do |line|
        break if line.strip == "USAGE"
        lines << line.strip unless line.strip.empty?
      end
      lines.join(" ")
    end

    def extract_positional(text)
      section = extract_section(text, "ARGUMENTS")
      return [] unless section

      section.lines.filter_map do |line|
        # Required: "  <name>  Description"
        # Optional: "  [name]  Description"
        if (m = line.match(/\A\s+<(\w[\w-]*)>\s+(.*)/))
          { "name" => m[1], "required" => true, "description" => m[2].strip }
        elsif (m = line.match(/\A\s+\[(\w[\w-]*)\]\s+(.*)/))
          { "name" => m[1], "required" => false, "description" => m[2].strip }
        end
      end
    end

    def extract_flags(text)
      section = extract_section(text, "FLAGS")
      return [] unless section

      flags = []
      # A flag line looks like:
      #   "  -d, --due string       Due date (YYYY-MM-DD)"
      #   "      --attach stringArray   Attach file (repeatable)"
      #   "  -h, --help             help for create"
      section.each_line do |line|
        next unless (m = line.match(/\A\s+(?:-(\w),\s+)?--([\w-]+)(?:\s+(\S+))?\s{2,}(.*)/))

        short, name, type_hint, desc = m[1], m[2], m[3], m[4].strip
        next if name == "help" # not useful as a tool parameter

        flags << {
          "name"        => name,
          "short"       => short,
          "type"        => map_type(type_hint),
          "description" => desc,
        }.compact
      end
      flags
    end

    def map_type(hint)
      case hint
      when nil               then "boolean"       # bare flag, no value
      when "stringArray"     then "array"
      when "int"             then "integer"
      when "bool"            then "boolean"
      else                        "string"
      end
    end

    # Extracts the body of a top-level section header like "FLAGS" or "ARGUMENTS"
    # up to the next top-level header or end of text.
    def extract_section(text, name)
      in_section = false
      out = +""
      text.each_line do |line|
        if line.start_with?(name) && line.strip == name
          in_section = true
          next
        end
        if in_section
          # Next section header: line starts at column 0 with uppercase word.
          break if line.match?(/\A[A-Z][A-Z ]+\z/) || line.match?(/\A[A-Z][A-Z ]+\n/)
          out << line
        end
      end
      in_section ? out : nil
    end
  end
end
