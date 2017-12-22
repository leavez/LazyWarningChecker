#!/usr/bin/python
# coding: utf-8

import os, subprocess, gzip, re
import argparse
import time

## represent a log file
class Log(object):
    def __init__(self, filePath):
        self.path = filePath
        self.lines = None
    
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

    # override 
    def parse(self):
        super(WarningLog, self).parse()
        self.lines = self.filterMeaningfulLines(self.lines)

    def filterMeaningfulLines(self, lines):
        return filter(lambda l: ": warning:" in l, lines)



class XcodeBuildData(object):
    def __init__(self, buildRootPath):
        self.rootPath = buildRootPath
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


def getArguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("BuildPath" ,help="the build path of xcode, use the value of $BUILD_ROOT of building")
    parser.add_argument("-o", help="write the result to path")
    args = parser.parse_args()
    # get argv
    return (args.BuildPath, args.o)

def writeResultToPath(path, passed):

    if not os.path.exists(path):
        dir = os.path.dirname(path)
        os.makedirs(dir)

    f = open(path, "w")
    content = "PASS" if passed else "NOT PASS"
    content += "\n"
    content += str(time.ctime())
    f.write(content)
    f.close()


if __name__ == "__main__":
    args = getArguments()
    build = XcodeBuildData(args[0])

    checker = Checker()
    checker.addRule(Checker.checkAllWarning)

    def doesPass():
        for log in build.warningLogs:
            log.parse()
            if checker.haveWarning(log):
                passed = False
        passed = True
    passed = doesPass()

    print( "PASS" if passed else "NOT PASS")
    outPath = args[1]
    if outPath:
        writeResultToPath(outPath, passed)
    
