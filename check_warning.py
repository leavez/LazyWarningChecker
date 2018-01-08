#!/usr/bin/python
# coding: utf-8

import os, subprocess, gzip, re
import argparse
import time, json

## represent a log file
class Log(object):

    # SLF0 is the format of xcactivitylog file
    class SLF0_Parser(object):
        TOKEN_INT            = '#'
        TOKEN_CLASS_NAME     = '%'
        TOKEN_CLASS_NAME_REF = '@'
        TOKEN_STRING         = '"'
        TOKEN_DOUBLE         = '^'
        OBJECT_LIST_NIL      = '-'
        OBJECT_LIST          = '('   
        symbols = set([TOKEN_INT, TOKEN_CLASS_NAME, TOKEN_CLASS_NAME_REF, TOKEN_STRING, TOKEN_DOUBLE, OBJECT_LIST_NIL, OBJECT_LIST])
        # reference https://github.com/americanexpress/xcode-result-bundle-processor/blob/bc91947f33db322a790895ecea9309aea7e6af55/lib/xcoderesultbundleprocessor/slf0/tokenizer.rb

        def __init__(self, io, onlyCareSymbol=None):
            if not self.isValidSLF0(io):
                raise Exception("Input is not a valid SLF0 format file", io)
            self.tokens = []
            while True:
                c = self.readAToken(io)
                if not c:
                    break
                self.tokens.append(c)
            pass

        def isValidSLF0(self, io):
            if io is None:
                return False 
            return io.read(4) == 'SLF0'

        @classmethod
        def readAToken(self, io):
            numberString = ""
            while True:
                c = io.read(1)
                if len(c) == 0 or c in self.symbols:
                    break
                numberString += c

            content = ""
            if c in [self.TOKEN_STRING, self.TOKEN_CLASS_NAME]:
                content = io.read(int(numberString))
            elif c in [self.TOKEN_INT, self.TOKEN_DOUBLE, self.OBJECT_LIST, self.TOKEN_CLASS_NAME_REF]:
                content = numberString
            else:
                content = ""
            
            if c == self.TOKEN_STRING:
                content = content.replace("\r", "\n")
                    
            if not c:
                return None
            else:
                return (content, c)


    def __init__(self, filePath):
        self.path = filePath
        self.lines = None
        self.parsedLines = None
    
    def getLinesOfXCLog(self, path):
        # return [string]
        f = gzip.open(path, mode="rb")
        tokens = Log.SLF0_Parser(f).tokens
        f.close()
        tokens = filter(lambda t: t[1] == Log.SLF0_Parser.TOKEN_STRING and "warning:" in t[0], tokens)
        texts = map(lambda t: t[0], tokens)
        lines = reduce(lambda initial, t: initial + t.split("\n"), texts, [])
        return lines

    def parse(self):
        self.lines = self.getLinesOfXCLog(self.path)


class WarningLog(Log):

    # parsed log object
    class WarningLine(object):
        
        # regex to match warning line
        class Matcher:
            # $1 = file_path
            # $2 = file_name
            # $3 = line number
            # $4 = reason
            # $5 = compiler flag
            COMPILE_WARNING = re.compile(r"^(\/?.+\/)(.*)(:.*:.*):\swarning:\s(.*)(\[[-a-zA-Z#]+\])?$")

            # $1 = ld prefix
            # $2 = warning message
            LD_WARNING_MATCHER = re.compile(r"^(ld: )warning: (.*)$")

            # @regex Captured groups
            # $1 = whole warning
            GENERIC_WARNING_MATCHER = re.compile(r"warning:\s(.*)$")

            # # @regex Captured groups
            # # $1 = whole warning
            # WILL_NOT_BE_CODE_SIGNED_MATCHER = re.compile(r"^(.* will not be code signed because .*)$")
            
        def __init__(self, lineText):
            self.parsed = False
            self.raw = lineText 
            self.isBrokenLine = False # the text cannot match our regex.
            self.isACompileWarning = False 
            
            # these properies ara only have valid value when self.isACompileWarning == True
            self.filePath = "" # /user/xxx/xxx/
            self.fileName = "" # abc.m
            self.lineNumber = "" # :123:12
            self.reason = "" # class AAA does not conform to protocol BBB
            self.flag = "" # -Wprotocol

        def parseIfNeeded(self):
            if self.parsed:
                return
            self.parsed = True

            MacherClass = WarningLog.WarningLine.Matcher
            result = MacherClass.COMPILE_WARNING.search(self.raw)
            if result:
                self.filePath = result.group(1)
                self.fileName = result.group(2)
                self.lineNumber = result.group(3)
                self.reason = result.group(4)
                self.flag = (result.group(5) or "").strip("[]")
                self.isACompileWarning = True
                return

            result = MacherClass.LD_WARNING_MATCHER.search(self.raw)
            if result:
                self.reason = result.group(0)
                return

            result = MacherClass.GENERIC_WARNING_MATCHER.search(self.raw)
            if result:
                self.reason = result.group(0)
                return

            # non-mached line
            self.isBrokenLine = True
            return
            

    # override 
    def parse(self):
        super(WarningLog, self).parse()
        self.lines = self.filterMeaningfulLines(self.lines)
        self.parsedLines = map(lambda t: WarningLog.WarningLine(t), self.lines)

    def filterMeaningfulLines(self, lines):
        return filter(lambda l: "warning:" in l, lines)



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

        # Just return when have first matched
        # this could speed up the process of checking
        self.returnWhenFistHit = config.showNonPassWarning == "first" 


    def haveWarning(self, log):
        # return [WarningLine], [] means have no warnings
        def filterOutExclusive(lines):
            # return filtered
            returnLines = lines
            for rule in self.exclusiveRules:
                returnLines = filter(lambda l: not rule.hit(l), returnLines)
            return returnLines

        hitLines = []
        for rule in self.rules:
            for line in log.parsedLines:
                line.parseIfNeeded()
                if rule.hit(line):
                    hitLines.append(line)
                    if self.returnWhenFistHit:
                        return filterOutExclusive(hitLines)
        return filterOutExclusive(hitLines)




class Config(object):
    def __init__(self, configFilePath):
        self.rules = []
        self.exclusiveRules = []
        self.showNonPassWarning = ""

        self.config = self.getConfig(configFilePath) or {}

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

        # show_non_pass_warning
        self.showNonPassWarning = self.config.get("show_non_pass_warning", "all")

    # demo config
    # --------------
    # 
    # "show_non_pass_warning": "all", # all, first
    # # default is all
    # "rules": [ 
    #     # { "type" : "regex", "content": "MWDataModel.m" },
    #     # { "type" : "flag", "content": "-Wunused-variable" },
    #     # { "type" : "flag", "content": "-W#warnings" },
    # ],
    # "exclusive_rules": [
    #     { "type": "flag", "content": "-Wnullability-completeness"},
    # ],
    #
    # ---------------
    def getConfig(self, configFilePath):
        if not configFilePath:
            return {}
        try:
            f = open(configFilePath, "r")
            config = f.read()
            jsonObject = json.loads(config)
            return jsonObject
        except IOError:
            print "connot open config file: %s" % configFilePath
            exit(1)
        except ValueError:
            print "config file is not a valid json: %s" % configFilePath
            exit(1)
        except:
            print "config is invalid: %s" % configFilePath
            exit(1)






class Output(object):
    def __init__(self):
        self.path = None
        self.warningLines = [] # [WarningLine]
        self.xcodeBuildData = None
        self.shouldShowCount = False

    def result(self):
        r = {
            "date": str(time.ctime()),
            "have_warning": len(self.warningLines) > 0,
            "build_path" : self.xcodeBuildData.rootPath,
        }
        if len(self.warningLines) > 0:
            def lineToText(line):
                if not line.isACompileWarning:
                    return line.raw
                reason = (line.fileName or "") + (line.lineNumber or "") + " -- " + (line.reason or "")
                if line.flag is not None and len(line.flag) > 0 :
                    reason += ("[" + line.flag + "]")
                return reason

            reasons = map(lineToText, self.warningLines)
            r["reason"] = reasons

        if self.shouldShowCount:
            r["matched_count"] = len(self.warningLines)
            
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
    parser.add_argument("-c", "--config", help = "the path of configuration file.")
    args = parser.parse_args()
    return args







if __name__ == "__main__":
    args = getArguments()
    build = XcodeBuildData(args.BuildPath)
    config = Config(args.config)

    checker = Checker(config)

    def checkWarningExisted():
        warnings = []
        for log in build.warningLogs:
            log.parse()
            result = checker.haveWarning(log)
            warnings.extend(result)
            if len(warnings) > 0 and checker.returnWhenFistHit:
                return warnings
        return warnings

    output = Output()
    output.warningLines = checkWarningExisted()
    output.xcodeBuildData = build
    output.shouldShowCount = not checker.returnWhenFistHit
    print output.result()

    outPath = args.o
    if outPath:
        output.path = outPath
        output.writeResult()
    
