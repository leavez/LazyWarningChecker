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
            regex = re.compile(r"(/.+\/)([^\/]+?\.[a-zA-Z]*)(:[0-9]+:[0-9]+)?: warning: (.+)(\[[-a-zA-Z]+\])$")
            result = regex.match(lineText)
            if result is None:
                self.brokenLine = True
                return 
            self.filePath = result.group(1)
            self.fileName = result.group(2)
            self.lineNumber = result.group(3)
            self.reason = result.group(4)
            self.flag = result.group(5)

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
    def __init__(self):
        self.rules = [] # list of function ( [string] -> Bool )

    def addRule(self, rule):
        self.rules.append(rule)


    @staticmethod
    def checkAllWarning(line):
        # if line is exsited, it's a warning line
        return line != None

    def haveWarning(self, log):
        # return Bool
        for rule in self.rules:
            for line in log.lines:
                if rule(line):
                    return True
        return False


class Output(object):
    def __init__(self):
        self.path = None
        self.haveWarning = False
        self.xcodeBuildData = None

    def result(self):
        r = {
            "date": str(time.ctime()),
            "have_warning": self.haveWarning,
            "build_path" : self.xcodeBuildData.rootPath,
        }
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

    checker = Checker()
    checker.addRule(Checker.checkAllWarning)

    def doesPass():
        for log in build.warningLogs:
            log.parse()
            if checker.haveWarning(log):
                passed = False
        passed = True
    passed = doesPass()

    output = Output()
    output.haveWarning = not passed
    output.xcodeBuildData = build
    print output.result()

    outPath = args.o
    if outPath:
        output.path = outPath
        output.writeResult()
    
