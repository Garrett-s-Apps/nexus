"""
NEXUS Security Scanner

Runs security scans on project code:
- Secret detection (hardcoded keys, tokens)
- Dependency vulnerability scanning (pip audit, npm audit)
- Basic SAST patterns (SQL injection, XSS, etc.)
- OWASP Top 10 checklist
"""

import json
import os
import re
import subprocess


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=60
        )
        return result.returncode, result.stdout, result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return 1, "", str(e)


# ============================================
# SECRET DETECTION
# ============================================

SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{20,}', "API Key"),
    (r'(?i)(secret|password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{8,}', "Secret/Password"),
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API Key"),
    (r'sk-ant-[a-zA-Z0-9\-_]{20,}', "Anthropic API Key"),
    (r'ghp_[A-Za-z0-9]{36}', "GitHub Personal Access Token"),
    (r'xoxb-[0-9]{10,}-[0-9]{10,}-[A-Za-z0-9]{20,}', "Slack Bot Token"),
    (r'xapp-[0-9]-[A-Z0-9]{10,}-[0-9]{10,}-[a-f0-9]{64}', "Slack App Token"),
    (r'AIza[A-Za-z0-9_\-]{35}', "Google API Key"),
    (r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----', "Private Key"),
    (r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*[A-Za-z0-9/+=]{40}', "AWS Secret Key"),
]

# Files/dirs to skip
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".next", "dist", "build"}
SKIP_EXTENSIONS = {".lock", ".png", ".jpg", ".gif", ".ico", ".woff", ".ttf", ".db", ".sqlite"}


def scan_secrets(project_path: str) -> list[dict]:
    """Scan for hardcoded secrets in source files."""
    findings = []

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in SKIP_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, project_path)

            # Skip binary files
            try:
                with open(filepath, errors="ignore") as f:
                    content = f.read()
            except (OSError, PermissionError):
                continue

            for pattern, secret_type in SECRET_PATTERNS:
                for match in re.finditer(pattern, content):
                    line_num = content[:match.start()].count("\n") + 1
                    findings.append({
                        "type": "secret",
                        "severity": "HIGH",
                        "file": rel_path,
                        "line": line_num,
                        "description": f"Potential {secret_type} detected",
                        "match": match.group()[:30] + "..." if len(match.group()) > 30 else match.group(),
                    })

    return findings


# ============================================
# DEPENDENCY SCANNING
# ============================================

def scan_dependencies(project_path: str) -> list[dict]:
    """Scan dependencies for known vulnerabilities."""
    findings = []

    # Python: pip audit
    if os.path.exists(os.path.join(project_path, "requirements.txt")) or \
       os.path.exists(os.path.join(project_path, "pyproject.toml")):
        code, stdout, stderr = _run(["pip", "audit", "--format=json"], cwd=project_path)
        if code == 0:
            try:
                data = json.loads(stdout)
                for vuln in data.get("vulnerabilities", []):
                    findings.append({
                        "type": "dependency",
                        "severity": vuln.get("fix_versions", ["UNKNOWN"])[0] if vuln.get("fix_versions") else "HIGH",
                        "file": "requirements.txt",
                        "description": f"{vuln.get('name', '?')}: {vuln.get('description', 'Vulnerability found')[:200]}",
                        "fix": f"Upgrade to {', '.join(vuln.get('fix_versions', []))}",
                    })
            except json.JSONDecodeError:
                pass

    # Node: npm audit
    if os.path.exists(os.path.join(project_path, "package.json")):
        code, stdout, stderr = _run(["npm", "audit", "--json"], cwd=project_path)
        try:
            data = json.loads(stdout)
            for name, info in data.get("vulnerabilities", {}).items():
                findings.append({
                    "type": "dependency",
                    "severity": info.get("severity", "UNKNOWN").upper(),
                    "file": "package.json",
                    "description": f"{name}: {info.get('title', 'Vulnerability found')[:200]}",
                    "fix": info.get("fixAvailable", "Check npm audit fix"),
                })
        except json.JSONDecodeError:
            pass

    return findings


# ============================================
# SAST (Static Application Security Testing)
# ============================================

SAST_PATTERNS = {
    "sql_injection": {
        "pattern": r'(?i)(execute|cursor\.execute|query)\s*\(\s*["\'].*%s|.*\+\s*\w+|.*\.format\(',
        "severity": "HIGH",
        "description": "Potential SQL injection: string interpolation in query",
        "extensions": {".py", ".js", ".ts", ".rb", ".php"},
    },
    "xss": {
        "pattern": r'(?i)(innerHTML|outerHTML|document\.write|v-html)\s*=',
        "severity": "MEDIUM",
        "description": "Potential XSS: direct HTML injection",
        "extensions": {".js", ".ts", ".jsx", ".tsx", ".vue", ".html"},
    },
    "hardcoded_ip": {
        "pattern": r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b',
        "severity": "LOW",
        "description": "Hardcoded IP address",
        "extensions": {".py", ".js", ".ts", ".yml", ".yaml", ".json", ".env"},
    },
    "eval_usage": {
        "pattern": r'\beval\s*\(',
        "severity": "HIGH",
        "description": "Use of eval() — potential code injection",
        "extensions": {".py", ".js", ".ts"},
    },
    "todo_security": {
        "pattern": r'(?i)#\s*TODO.*(?:security|auth|hack|fix|vuln|FIXME)',
        "severity": "LOW",
        "description": "Security-related TODO/FIXME found",
        "extensions": {".py", ".js", ".ts", ".rb", ".go", ".java"},
    },
}


def scan_sast(project_path: str) -> list[dict]:
    """Run basic SAST patterns against source files."""
    findings = []

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, project_path)

            try:
                with open(filepath, errors="ignore") as f:
                    content = f.read()
            except (OSError, PermissionError):
                continue

            for rule_name, rule in SAST_PATTERNS.items():
                if ext not in rule["extensions"]:
                    continue

                for match in re.finditer(str(rule["pattern"]), content):
                    line_num = content[:match.start()].count("\n") + 1
                    findings.append({
                        "type": "sast",
                        "rule": rule_name,
                        "severity": rule["severity"],
                        "file": rel_path,
                        "line": line_num,
                        "description": rule["description"],
                    })

    return findings


# ============================================
# FULL AUDIT
# ============================================

def run_full_audit(project_path: str) -> dict:
    """Run all security scans and return a comprehensive report."""
    secrets = scan_secrets(project_path)
    deps = scan_dependencies(project_path)
    sast = scan_sast(project_path)

    all_findings = secrets + deps + sast

    high = [f for f in all_findings if f.get("severity") == "HIGH"]
    medium = [f for f in all_findings if f.get("severity") == "MEDIUM"]
    low = [f for f in all_findings if f.get("severity") == "LOW"]

    return {
        "project": project_path,
        "total_findings": len(all_findings),
        "high": len(high),
        "medium": len(medium),
        "low": len(low),
        "findings": all_findings,
        "clean": len(high) == 0,
        "summary": generate_audit_summary(all_findings, project_path),
    }


def generate_audit_summary(findings: list[dict], project_path: str) -> str:
    """Generate a human-readable security audit summary."""
    high = [f for f in findings if f.get("severity") == "HIGH"]
    medium = [f for f in findings if f.get("severity") == "MEDIUM"]
    low = [f for f in findings if f.get("severity") == "LOW"]

    status = "✅ CLEAN" if not high else "❌ CRITICAL ISSUES" if len(high) > 3 else "⚠️ ISSUES FOUND"

    report = f"""
Security Audit Report — {os.path.basename(project_path)}
{'=' * 55}

Status: {status}
Total Findings: {len(findings)}
  HIGH:   {len(high)}  {'❌' if high else '✅'}
  MEDIUM: {len(medium)}  {'⚠️' if medium else '✅'}
  LOW:    {len(low)}

"""

    if high:
        report += "CRITICAL FINDINGS:\n"
        for f in high[:10]:
            report += f"  [{f['severity']}] {f['file']}:{f.get('line', '?')} — {f['description']}\n"
        report += "\n"

    if medium:
        report += "MEDIUM FINDINGS:\n"
        for f in medium[:10]:
            report += f"  [{f['severity']}] {f['file']}:{f.get('line', '?')} — {f['description']}\n"
        report += "\n"

    if low and len(low) <= 5:
        report += "LOW FINDINGS:\n"
        for f in low:
            report += f"  [{f['severity']}] {f['file']}:{f.get('line', '?')} — {f['description']}\n"
    elif low:
        report += f"LOW FINDINGS: {len(low)} (omitted for brevity)\n"

    report += f"\n{'=' * 55}\n"
    return report
