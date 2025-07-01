#!/usr/bin/env python3

# Script to add UID-based JavaScript functions to models.py


def add_uid_functions():
    # Read the file
    with open("src/syft_code_queue/models.py") as f:
        content = f.read()

    # Find the position to insert the new functions (before </script>)
    script_end = content.find("        </script>")
    if script_end == -1:
        print("Could not find </script> tag")
        return

    # Define the new functions
    new_functions = """
        // UID-based functions for individual row buttons
        window.approveJobByUid = function(jobUid) {
            var reason = prompt("Approval reason (optional):", "Approved via Jupyter interface");
            if (reason !== null) {
                var code = `q.get_job("${jobUid}").approve("${reason.replace(/"/g, '\\\\"')}")`;

                navigator.clipboard.writeText(code).then(() => {
                    var buttons = document.querySelectorAll(`button[onclick="approveJobByUid('${jobUid}')"]`);
                    buttons.forEach(button => {
                        var originalText = button.innerHTML;
                        button.innerHTML = '✅ Copied!';
                        button.style.backgroundColor = '#059669';
                        setTimeout(() => {
                            button.innerHTML = originalText;
                            button.style.backgroundColor = '';
                        }, 2000);
                    });
                }).catch(err => {
                    console.error('Could not copy code to clipboard:', err);
                    alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
                });
            }
        };

        window.rejectJobByUid = function(jobUid) {
            var reason = prompt("Rejection reason:", "");
            if (reason !== null && reason.trim() !== "") {
                var code = `q.get_job("${jobUid}").reject("${reason.replace(/"/g, '\\\\"')}")`;

                navigator.clipboard.writeText(code).then(() => {
                    var buttons = document.querySelectorAll(`button[onclick="rejectJobByUid('${jobUid}')"]`);
                    buttons.forEach(button => {
                        var originalText = button.innerHTML;
                        button.innerHTML = '🚫 Copied!';
                        button.style.backgroundColor = '#dc2626';
                        setTimeout(() => {
                            button.innerHTML = originalText;
                            button.style.backgroundColor = '';
                        }, 2000);
                    });
                }).catch(err => {
                    console.error('Could not copy code to clipboard:', err);
                    alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
                });
            }
        };

        window.reviewJobByUid = function(jobUid) {
            var code = `q.get_job("${jobUid}").review()`;

            navigator.clipboard.writeText(code).then(() => {
                var buttons = document.querySelectorAll(`button[onclick="reviewJobByUid('${jobUid}')"]`);
                buttons.forEach(button => {
                    var originalText = button.innerHTML;
                    button.innerHTML = '📋 Copied!';
                    button.style.backgroundColor = '#059669';
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.style.backgroundColor = '';
                    }, 2000);
                });
            }).catch(err => {
                console.error('Could not copy code to clipboard:', err);
                alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
            });
        };

        window.viewLogsByUid = function(jobUid) {
            var code = `q.get_job("${jobUid}").get_logs()`;

            navigator.clipboard.writeText(code).then(() => {
                var buttons = document.querySelectorAll(`button[onclick="viewLogsByUid('${jobUid}')"]`);
                buttons.forEach(button => {
                    var originalText = button.innerHTML;
                    button.innerHTML = '📜 Copied!';
                    button.style.backgroundColor = '#6366f1';
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.style.backgroundColor = '';
                    }, 2000);
                });
            }).catch(err => {
                console.error('Could not copy code to clipboard:', err);
                alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
            });
        };

        window.viewOutputByUid = function(jobUid) {
            var code = `q.get_job("${jobUid}").get_output()`;

            navigator.clipboard.writeText(code).then(() => {
                var buttons = document.querySelectorAll(`button[onclick="viewOutputByUid('${jobUid}')"]`);
                buttons.forEach(button => {
                    var originalText = button.innerHTML;
                    button.innerHTML = '📁 Copied!';
                    button.style.backgroundColor = '#8b5cf6';
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.style.backgroundColor = '';
                    }, 2000);
                });
            }).catch(err => {
                console.error('Could not copy code to clipboard:', err);
                alert('Failed to copy to clipboard. Please copy manually:\\\\n\\\\n' + code);
            });
        };
"""

    # Insert the new functions
    new_content = content[:script_end] + new_functions + content[script_end:]

    # Write back to file
    with open("src/syft_code_queue/models.py", "w") as f:
        f.write(new_content)

    print("Successfully added UID-based JavaScript functions")


if __name__ == "__main__":
    add_uid_functions()
