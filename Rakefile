require "json"
require_relative "lib/basecamp_mcp/generator"

namespace :tools do
  desc "Regenerate data/tools.json by introspecting the basecamp CLI"
  task :generate do
    out = File.expand_path("data/tools.json", __dir__)
    tools = BasecampMcp::Generator.new.generate
    File.write(out, JSON.pretty_generate(tools) + "\n")
    puts "Wrote #{tools.size} tools to #{out}"
  end
end

require "rake/testtask"
Rake::TestTask.new(:test) do |t|
  t.libs << "test" << "lib"
  t.test_files = FileList["test/**/*_test.rb"]
  t.warning = false
end

task default: :test
