# TOOLS.md - Available Tool Definitions

## File Operations

### read_file
```json
{
  "name": "read_file",
  "description": "Read the contents of a file at the specified path",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Absolute or relative path to the file"
      },
      "encoding": {
        "type": "string",
        "description": "File encoding (default: utf-8)",
        "default": "utf-8"
      }
    },
    "required": ["path"]
  }
}
```

### write_file
```json
{
  "name": "write_file",
  "description": "Write content to a file at the specified path",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Absolute or relative path to the file"
      },
      "content": {
        "type": "string",
        "description": "Content to write to the file"
      },
      "mode": {
        "type": "string",
        "enum": ["overwrite", "append"],
        "default": "overwrite"
      }
    },
    "required": ["path", "content"]
  }
}
```

### list_directory
```json
{
  "name": "list_directory",
  "description": "List files and directories at the specified path",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Directory path to list"
      },
      "recursive": {
        "type": "boolean",
        "description": "Whether to list recursively",
        "default": false
      },
      "pattern": {
        "type": "string",
        "description": "Glob pattern to filter results"
      }
    },
    "required": ["path"]
  }
}
```

## Shell Operations

### execute_command
```json
{
  "name": "execute_command",
  "description": "Execute a shell command in the workspace",
  "parameters": {
    "type": "object",
    "properties": {
      "command": {
        "type": "string",
        "description": "The shell command to execute"
      },
      "working_directory": {
        "type": "string",
        "description": "Working directory for the command"
      },
      "timeout": {
        "type": "integer",
        "description": "Timeout in seconds",
        "default": 120
      }
    },
    "required": ["command"]
  }
}
```

## Search Operations

### grep_search
```json
{
  "name": "grep_search",
  "description": "Search for a pattern in files using regex",
  "parameters": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "Regex pattern to search for"
      },
      "path": {
        "type": "string",
        "description": "Directory or file to search in"
      },
      "file_pattern": {
        "type": "string",
        "description": "Glob pattern to filter files (e.g., '*.py')"
      },
      "case_sensitive": {
        "type": "boolean",
        "default": true
      },
      "max_results": {
        "type": "integer",
        "default": 100
      }
    },
    "required": ["pattern"]
  }
}
```

### glob_search
```json
{
  "name": "glob_search",
  "description": "Find files matching a glob pattern",
  "parameters": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "Glob pattern (e.g., '**/*.py')"
      },
      "path": {
        "type": "string",
        "description": "Base directory to search from"
      }
    },
    "required": ["pattern"]
  }
}
```

## Code Analysis

### analyze_code
```json
{
  "name": "analyze_code",
  "description": "Analyze code for issues, complexity, and suggestions",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "File or directory to analyze"
      },
      "checks": {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["lint", "type", "complexity", "security"]
        },
        "description": "Types of analysis to perform"
      }
    },
    "required": ["path"]
  }
}
```

## Git Operations

### git_status
```json
{
  "name": "git_status",
  "description": "Get the current git status",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Repository path"
      }
    }
  }
}
```

### git_diff
```json
{
  "name": "git_diff",
  "description": "Show git diff for files",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "File or directory to diff"
      },
      "staged": {
        "type": "boolean",
        "description": "Show staged changes only",
        "default": false
      }
    }
  }
}
```

### git_log
```json
{
  "name": "git_log",
  "description": "Show git commit history",
  "parameters": {
    "type": "object",
    "properties": {
      "count": {
        "type": "integer",
        "description": "Number of commits to show",
        "default": 10
      },
      "path": {
        "type": "string",
        "description": "Filter by file path"
      }
    }
  }
}
```
