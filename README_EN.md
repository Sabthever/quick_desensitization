# Quick Desensitization Tool (脱敏小工具)

A desktop application to desensitize sensitive data in project configuration files, making it safe to share projects with AI coding assistants.

## Overview

As AI coding assistants become increasingly prevalent in software development, developers often want to leverage AI to help debug, refactor, or enhance their code. However, project configuration files typically contain sensitive information such as:

- Database passwords and connection strings
- API keys and access tokens
- Private certificates and keys
- Service credentials
- Cloud platform secrets

**Quick Desensitization Tool** solves this problem by allowing you to:

1. **Desensitize** your project — replace sensitive values with safe placeholders
2. **Share** the desensitized project with AI tools with confidence
3. **Restore** the original sensitive values when needed

## Features

- **Multi-format Support**: Works with YAML, ENV, and JSON configuration files
- **Flexible Rules**: Configure which fields to desensitize using wildcard patterns
- **Safe Storage**: Original values are stored separately with Base64 encoding
- **Backup System**: Automatic backups before any modifications
- **Project Management**: Manage multiple projects with different configurations
- **One-click Restore**: Restore all original values with a single click
- **GUI Interface**: User-friendly desktop application (Chinese interface)
- **Ready-to-Run EXE**: Download and double-click to run, no setup needed
- **Batch Operations**: Multi-select rules for batch delete, enable/disable
- **Import/Export**: Import and export desensitization rules for reuse

## Installation

### Quick Start (Recommended)

If you just want to run the application without installing Python or dependencies:

```bash
# Download the latest release and double-click the .exe file
```

That's it! No installation required.

### From Source

If you want to run from source or contribute to development:

#### Prerequisites

- Python 3.8+
- pip

#### Steps

```bash
# Clone or navigate to the project directory
cd quick_desensitization

# Install dependencies
pip install -r requirements.txt
```

#### Run

```bash
python src/main.py
```

Or simply double-click `run.bat` on Windows.

## Usage

### 1. Add a New Project

Click **+ 新增项目** and configure:

- **Project Path**: Select your project root directory
- **Secret Path**: Choose a location outside your project to store sensitive data

![Project Page](image/项目页面.png)

### 2. Configure Desensitization Rules

Click **编辑** on a project, then **+ 新增规则** to add rules:

![Edit Interface](image/编辑界面.png)

| File Type | Description | Example Field Path |
|-----------|-------------|-------------------|
| `yml` | YAML files | `spring.datasource.password` |
| `env` | Environment files | `DB_PASSWORD` |
| `json` | JSON files (JSONPath) | `$.database.password` |

![New Entry Interface](image/新增界面.png)

#### Field Path Examples

**YAML:**
```
spring.datasource.password          # Exact match
spring.datasource.*.password        # Match one level
spring.datasource.**.password       # Match any level (recursive)
```

**ENV:**
```
DB_PASSWORD                         # Exact key name
DB_*                                # All keys starting with DB_
*_PASSWORD                           # All keys ending with _PASSWORD
```

**JSON (JSONPath):**
```
$.database.password                 # Exact path
$..password                         # Recursive match (any location)
$.database.*.password               # Wildcard match
```

#### Batch Operations & Import/Export

Multi-select operations are supported in the rule list:

- **Ctrl + Click**: Select multiple non-contiguous rules
- **Shift + Click**: Select a range of rules
- **Ctrl + A**: Select all

After selecting rules, you can batch delete, enable/disable rules.

Click **导入规则** to import rules from a CSV file (duplicate rules will be skipped). Click **导出选中规则** to export selected rules to a CSV file.

### 3. Desensitize

Click **脱敏** on a project to:

1. Scan all matching files in the project
2. Replace sensitive values with placeholders like `${val_abc123}`
3. Store original values in the secret path
4. Create backups automatically

### 4. Share with AI

Your project is now safe to share! The placeholder values provide no useful information to external parties.

### 5. Restore

When you receive help from AI and need the original values back:

1. Click **恢复** on the project
2. All original values will be restored from the secret storage
3. **Important**: After debugging, run **脱敏** again to protect your data!

## File Structure

```
quick_desensitization/
├── src/
│   ├── main.py                 # Application entry point
│   ├── desensitize_engine.py   # Core desensitization logic
│   ├── storage.py              # Data persistence layer
│   └── ui/
│       └── main_window.py      # GUI components
├── requirements.txt        # Python dependencies
└── run.bat                 # Windows launcher
```

## How It Works

### Desensitization Process

```
Original Value:  my_secret_password
        ↓
Placeholder:      ${val_a1b2c3d4e5f6}
        ↓
Stored in:       secret.csv (secret path, Base64 encoded)
```

### Security Design

- **Separation**: Secret path must be outside project path
- **Encoding**: Original values stored with Base64 encoding
- **Backups**: Original files backed up before modification
- **No Network**: All processing is local, nothing is transmitted

## Configuration Files

### secret_config.csv

Located in your secret path, defines desensitization rules:

```csv
yml,application*.yml,spring.datasource.password,true
env,.env,DB_PASSWORD,true
json,config.json,$.api.key,true
```

### secret.csv

Located in your secret path, stores the original sensitive values (Base64 encoded):

```csv
# 敏感信息存储文件
# 格式: 文件路径,字段路径,占位符,原始值(Base64),脱敏时间
```

## Dependencies

- **PySide6**: Qt for Python (GUI framework)
- **PyYAML**: YAML parsing
- **ruamel.yaml**: YAML handling with quote preservation

## Use Cases

### Scenario 1: AI Code Review

1. You have a Spring Boot project with database credentials
2. Before sharing with an AI code reviewer, run **脱敏**
3. Share the desensitized project — no real credentials exposed
4. After getting suggestions, run **恢复** to restore credentials

### Scenario 2: AI Debugging

1. Your microservice has API keys in `.env` files
2. Run **脱敏** before pasting code to AI
3. Get debugging help from AI assistant
4. Run **恢复** to restore working configuration

### Scenario 3: AI Refactoring

1. Project contains encrypted database passwords in YAML
2. Desensitize with pattern `**.password`
3. Use AI to refactor configuration management
4. Restore original passwords after changes verified

## License

MIT License

## Disclaimer

This tool is provided as-is. Always verify your sensitive data is properly protected before sharing with any external service. The developers are not responsible for any data exposure caused by improper use.
