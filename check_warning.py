#!/usr/bin/python
# coding: utf-8

import os, subprocess, gzip, re
import argparse
import time, json

## represent a log file
class Log(object):
    def __init__(self, filePath):
        self.path = filePath
        self.lines = None
        self.parsedLines = None
    
    def getLinesOfXCLog(self, path):
        # return [string]
        f = gzip.open(path, mode="rb")
        content = f.readlines()
        content = reduce(lambda initial, line: initial + line.split("\r") , content, [])
        f.close()
        return content

    def parse(self):
        self.lines = self.getLinesOfXCLog(self.path)


class WarningLog(Log):

    # parsed log object
    class WarningLine(object):
        def __init__(self, lineText):
            self.parsed = False
            self.raw = lineText 
            self.filePath = "" # /user/xxx/xxx/
            self.fileName = "" # abc.m
            self.lineNumber = "" # :123:12
            self.reason = "" # class AAA does not conform to protocol BBB
            self.flag = "" # -Wprotocol
            self.brokenLine = False # the text cannot match our regex. In this situation, all other properies are meaningles.

        def parseIfNeeded(self):
            if self.parsed:
                return
            self.parsed = True
            regex = re.compile(r"(/.+\/)([^\/]+?\.[a-zA-Z]*)(:[0-9]+:[0-9]+)?: warning: (.+?)(\[[-a-zA-Z#]+\])?$")
            result = regex.search(self.raw)
            if result is None:
                self.brokenLine = True
                print "regex cannot match this line:", self.raw
                return 
            self.filePath = result.group(1)
            self.fileName = result.group(2)
            self.lineNumber = result.group(3)
            self.reason = result.group(4)
            self.flag = result.group(5)
            if self.flag:
                self.flag = self.flag.strip("[]")

    # override 
    def parse(self):
        super(WarningLog, self).parse()
        self.lines = self.filterMeaningfulLines(self.lines)
        self.parsedLines = map(lambda t: WarningLog.WarningLine(t), self.lines)

    def filterMeaningfulLines(self, lines):
        return filter(lambda l: ": warning:" in l, lines)



class XcodeBuildData(object):
    def __init__(self, buildRoot):
        self.rootPath = os.path.dirname(os.path.dirname(buildRoot))
        self.warningPath = os.path.join(self.rootPath, "Logs/Issues")

        # find all warning log path
        warningPaths = filter(lambda p: p.endswith("xcactivitylog"), os.listdir(self.warningPath))
        warningPaths = map(lambda p: os.path.join(self.warningPath, p), warningPaths)
        self.warningLogFilePaths = warningPaths
        self.warningLogs = map(lambda p: WarningLog(p), self.warningLogFilePaths)

        

class Checker(object):

    class Rule(object):
        def __init__(self, jsonDict):
            # all / regex / flag  
            # for "flag", https://clang.llvm.org/docs/DiagnosticsReference.html
            self.type = jsonDict.get("type", "")
            self.content = jsonDict.get("content", "")

            self.regex = None
            try:
                self.regex = re.compile(self.content)
            except:
                print "regex format is invalide: %s" % self.content
                exit(1)

        def hit(self, lineObject):
            # line: a WarningLine object
            # return bool
            def all(line):
                return lineObject != None

            def flag(line):
                return self.content == line.flag

            def regex(line):
                return self.regex.search(line.raw) != None

            return {
                "all" : all,
                "regex": regex,
                "flag": flag,
            }[self.type](lineObject)

        @staticmethod
        def checkAll():
            rule = Checker.Rule({"type": "all"})
            return rule


    def __init__(self, config):
        # config: Config object
        self.rules = config.rules or []
        self.exclusiveRules = config.exclusiveRules or []


    def haveWarning(self, log):
        # return [WarningLine], [] means have no warnings
        hitLines = []
        for rule in self.rules:
            for line in log.parsedLines:
                line.parseIfNeeded()
                if rule.hit(line):
                    hitLines.append(line)
                    return hitLines
        return []




class Config(object):
    def __init__(self):
        self.rules = []
        self.exclusiveRules = []

        self.config = self.getConfig()

        # rules
        rulesConfig = self.config.get("rules")
        if rulesConfig == None:
            self.rules.append(Checker.Rule.checkAll())
        else:
            self.rules = map(lambda json: Checker.Rule(json), rulesConfig)

        # exclusive rules
        rulesConfig = self.config.get("exclusive_rules")
        if rulesConfig:
            self.exclusiveRules = map(lambda json: Checker.Rule(json), rulesConfig)

        # TODO
        # show_warning_count
        # show_non_pass_warning


    def getConfig(self):

        return {
            "show_warning_count": True,
            "show_non_pass_warning": "first", # all, first, none
            "rules": [ # default is all
                { "type" : "flag", "content": "-Wunused-variable" },
                # { "type" : "regex", "content": "" },
                # { "type" : "regex", "content": "" },
                # { "type" : "regex", "content": "" },
            ],
            "exclusive_rules": [
                { "type": "flag", "content": "-Wnullability-completeness"},
            ],
        }


class Output(object):
    def __init__(self):
        self.path = None
        self.warningLines = [] # [WarningLine]
        self.xcodeBuildData = None

    def result(self):
        r = {
            "date": str(time.ctime()),
            "have_warning": len(self.warningLines) > 0,
            "build_path" : self.xcodeBuildData.rootPath,
        }
        if len(self.warningLines) > 0:
            line = self.warningLines[0]
            reason = line.fileName + line.lineNumber + "  " + line.reason
            if len(line.flag) > 0 :
                reason += ("[" + line.flag + "]")
            r["reason"] = reason
            
        return json.dumps(r,indent=4)

    def writeResult(self):
        path = self.path
        if not os.path.exists(path):
            dir = os.path.dirname(path)
            if not os.path.exists(dir):
                os.makedirs(dir)

        f = open(self.path, "w+")
        content = self.result()
        f.write(content)
        f.close()


def getArguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("BuildPath" ,help="the build path of xcode, use the value of $BUILD_ROOT of building")
    parser.add_argument("-o", help="write the result to path")
    args = parser.parse_args()
    # get argv
    return args







if __name__ == "__main__":
    args = getArguments()
    build = XcodeBuildData(args.BuildPath)

    checker = Checker(Config())

    def checkWarningExisted():
        for log in build.warningLogs:
            log.parse()
            result = checker.haveWarning(log)
            if result:
                return result
        return []

    output = Output()
    output.warningLines = checkWarningExisted()
    output.xcodeBuildData = build
    print output.result()

    outPath = args.o
    if outPath:
        output.path = outPath
        output.writeResult()
    
