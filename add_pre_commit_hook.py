#!/usr/bin/python
# encoding: utf-8

import os, stat, subprocess
import argparse

class HookHelper(object):
    def __init__(self, aProjectPath):
        self.repoPath = subprocess.check_output("cd %s; git rev-parse --show-toplevel" % aProjectPath, shell=True).strip()

    def writeToHooks(self):
        preCommitPath = os.path.join(self.repoPath, ".git/hooks/pre-commit")

        # Check if already have a pre-commit hook
        if os.path.exists(preCommitPath):
            f = open(preCommitPath, "r")
            content = f.read()
            f.close()
            if content != HookHelper.content():
                print "Pre-commit hooks exsited! Fail to write pre-commit hook."
                return
            else:
                # Already wrote. Just return.
                return
        
        # write file
        f = open(preCommitPath, "w+")
        f.write(HookHelper.content())
        f.close()
        st = os.stat(preCommitPath)
        os.chmod(preCommitPath, st.st_mode | stat.S_IEXEC)

    @staticmethod
    def content():
        return """#!/usr/bin/python
import os.path
import sys
import json

# check the warning checker's result
# if have warnings, we prevent the commintting

path = ".warning_checker/last_result"
haveCachedResult = os.path.isfile(path)
if not haveCachedResult:
    # nothing wrong. exit.
    exit(0)

f = open(path, "r")
content = f.read()
f.close()
result = json.loads(content)

haveWarnings = result.get("have_warning", False)
if haveWarnings:
    ret = "\\n"
    sys.stderr.write(ret)
    sys.stderr.write("   Please relove the build warnings before committing."+ret)
    sys.stderr.write("   (You should rebuild the project to update the checking result.)"+ret+ret)
    warning = ""
    count = result.get("matched_count")
    if count:
        warning += "match %s warning(s):" % str(count) + ret
    reason = result.get("reason", [])
    if len(reason) > 20:
        reason = reason[:20]
    warning += ret.join(reason)
    sys.stderr.write(warning)
    exit(1)
    """


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    # add hook parser
    add = subparsers.add_parser("add", help="add pre-commit hook directly to .git directory")
    add.add_argument("soure_path" ,help="any path in the repository's path")
    
    # print content parser
    subparsers.add_parser("raw", help = "print hook script to stdout")
    args = parser.parse_args()

    if args.command == "add":
        HookHelper(args.soure_path).writeToHooks()
    elif args.command == "raw":
        print HookHelper.content()
        
