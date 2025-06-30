#!/usr/bin/env python3

def add_javascript_functions():
    # Read the file
    with open('src/syft_code_queue/models.py', 'r') as f:
        content = f.read()
    
    # Find the insertion point (before the closing """)
    lines = content.split('\n')
    
    # Find the line with """ that closes the JavaScript section
    insert_line = None
    for i, line in enumerate(lines):
        if line.strip() == '"""' and i > 1400:  # Look for the """ after the JavaScript section
            insert_line = i
            break
    
    if insert_line is None:
        print("Could not find the insertion point")
        return
    
    # JavaScript functions to add
    js_functions = [
        "",
        "        // UID-based functions for individual row buttons",
        "        window.approveJobByUid = function(jobUid) {",
        "            var reason = prompt(\"Approval reason (optional):\", \"Approved via Jupyter interface\");",
        "            if (reason !== null) {",
        "                var code = `q.get_job(\"${jobUid}\").approve(\"${reason.replace(/\"/g, '\\\\\"')}\")`;",
        "",
        "                navigator.clipboard.writeText(code).then(() => {",
        "                    var buttons = document.querySelectorAll(`button[onclick=\"approveJobByUid('${jobUid}')\"]`);",
        "                    buttons.forEach(button => {",
        "                        var originalText = button.innerHTML;",
        "                        button.innerHTML = '✅ Copied!';",
        "                        button.style.backgroundColor = '#059669';",
        "                        setTimeout(() => {",
        "                            button.innerHTML = originalText;",
        "                            button.style.backgroundColor = '';",
        "                        }, 2000);",
        "                    });",
        "                }).catch(err => {",
        "                    console.error('Could not copy code to clipboard:', err);",
        "                    alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);",
        "                });",
        "            }",
        "        };",
        "",
        "        window.rejectJobByUid = function(jobUid) {",
        "            var reason = prompt(\"Rejection reason:\", \"\");",
        "            if (reason !== null && reason.trim() !== \"\") {",
        "                var code = `q.get_job(\"${jobUid}\").reject(\"${reason.replace(/\"/g, '\\\\\"')}\")`;",
        "",
        "                navigator.clipboard.writeText(code).then(() => {",
        "                    var buttons = document.querySelectorAll(`button[onclick=\"rejectJobByUid('${jobUid}')\"]`);",
        "                    buttons.forEach(button => {",
        "                        var originalText = button.innerHTML;",
        "                        button.innerHTML = '🚫 Copied!';",
        "                        button.style.backgroundColor = '#dc2626';",
        "                        setTimeout(() => {",
        "                            button.innerHTML = originalText;",
        "                            button.style.backgroundColor = '';",
        "                        }, 2000);",
        "                    });",
        "                }).catch(err => {",
        "                    console.error('Could not copy code to clipboard:', err);",
        "                    alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);",
        "                });",
        "            }",
        "        };",
        "",
        "        window.reviewJobByUid = function(jobUid) {",
        "            var code = `q.get_job(\"${jobUid}\").review()`;",
        "",
        "            navigator.clipboard.writeText(code).then(() => {",
        "                var buttons = document.querySelectorAll(`button[onclick=\"reviewJobByUid('${jobUid}')\"]`);",
        "                buttons.forEach(button => {",
        "                    var originalText = button.innerHTML;",
        "                    button.innerHTML = '📋 Copied!';",
        "                    button.style.backgroundColor = '#059669';",
        "                    setTimeout(() => {",
        "                        button.innerHTML = originalText;",
        "                        button.style.backgroundColor = '';",
        "                    }, 2000);",
        "                });",
        "            }).catch(err => {",
        "                console.error('Could not copy code to clipboard:', err);",
        "                alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);",
        "            });",
        "        };",
        "",
        "        window.viewLogsByUid = function(jobUid) {",
        "            var code = `q.get_job(\"${jobUid}\").get_logs()`;",
        "",
        "            navigator.clipboard.writeText(code).then(() => {",
        "                var buttons = document.querySelectorAll(`button[onclick=\"viewLogsByUid('${jobUid}')\"]`);",
        "                buttons.forEach(button => {",
        "                    var originalText = button.innerHTML;",
        "                    button.innerHTML = '📜 Copied!';",
        "                    button.style.backgroundColor = '#6366f1';",
        "                    setTimeout(() => {",
        "                        button.innerHTML = originalText;",
        "                        button.style.backgroundColor = '';",
        "                    }, 2000);",
        "                });",
        "            }).catch(err => {",
        "                console.error('Could not copy code to clipboard:', err);",
        "                alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);",
        "            });",
        "        };",
        "",
        "        window.viewOutputByUid = function(jobUid) {",
        "            var code = `q.get_job(\"${jobUid}\").get_output()`;",
        "",
        "            navigator.clipboard.writeText(code).then(() => {",
        "                var buttons = document.querySelectorAll(`button[onclick=\"viewOutputByUid('${jobUid}')\"]`);",
        "                buttons.forEach(button => {",
        "                    var originalText = button.innerHTML;",
        "                    button.innerHTML = '📁 Copied!';",
        "                    button.style.backgroundColor = '#8b5cf6';",
        "                    setTimeout(() => {",
        "                        button.innerHTML = originalText;",
        "                        button.style.backgroundColor = '';",
        "                    }, 2000);",
        "                });",
        "            }).catch(err => {",
        "                console.error('Could not copy code to clipboard:', err);",
        "                alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);",
        "            });",
        "        };"
    ]
    
    # Insert the functions before the closing """
    for i, js_line in enumerate(js_functions):
        lines.insert(insert_line + i, js_line)
    
    # Write back to file
    with open('src/syft_code_queue/models.py', 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Successfully added JavaScript functions at line {insert_line}")

if __name__ == "__main__":
    add_javascript_functions()
