import glob, json, os, random, re

from CommandTemplate import CommandTemplate
from IrcMessage import IrcMessage
import SharedFunctions
import GlobalStore


class Command(CommandTemplate):
	triggers = ['generate', 'gen']
	helptext = "Generate random stories or words. Call a specific generator with '{commandPrefix}generate [genName]'. Enter 'random' to let me pick, or choose from: "

	generators = {}
	filesLocation = os.path.join(GlobalStore.scriptfolder, "data", "generators")

	def onLoad(self):
		#First fill the generators dict with a few built-in generators
		self.generators = {self.generateName: 'name', self.generateVideogame: ('game', 'videogame'), self.generateWord: 'word', self.generateWord2: 'word2'}
		#Go through all available .grammar files and store their 'triggers'
		for grammarFilename in glob.iglob(os.path.join(self.filesLocation, '*.grammar')):
			with open(grammarFilename, 'r') as grammarFile:
				try:
					grammarJson = json.load(grammarFile)
				except ValueError as e:
					self.logError("[Generators] Error parsing grammar file '{}', invalid JSON: {}".format(grammarFilename, e.message))
				else:
					self.generators[grammarFilename] = tuple(grammarJson['_triggers'])
		#Add all the available triggers to the module's helptext
		self.helptext += ", ".join(self.getAvailableTriggers())
		self.logDebug("[Generators] Loaded {:,} generators".format(len(self.generators)))

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""

		if message.messagePartsLength == 0 or message.messageParts[0].lower() == 'help':
			return message.reply(self.getHelp(message))

		wantedGeneratorName = message.messageParts[0].lower()
		wantedGenerator = None

		if wantedGeneratorName == 'random':
			wantedGenerator = random.choice(self.generators.keys())
		else:
			#Check to see if it's a registered generator
			for generator, triggers in self.generators.iteritems():
				if isinstance(triggers, basestring):
					triggers = (triggers,)
				for trigger in triggers:
					if trigger == wantedGeneratorName:
						wantedGenerator = generator
						break
				if wantedGenerator is not None:
					break

		if wantedGenerator is None:
			#No suitable generator found, list the available ones
			message.reply("That is not a valid generator name. Use 'random' to let me pick, or choose from: {}".format(", ".join(self.getAvailableTriggers())))
		else:
			parameters = message.messageParts[1:]
			#The generator can either be a module function, or a string pointing to a grammar file. Check which it is
			if isinstance(wantedGenerator, basestring):
				#Grammar file! Send it to the parser
				message.reply(self.parseGrammarFile(wantedGenerator, parameters=parameters))
			else:
				#Function! Just call it, with the message so it can figure it out from there itself
				message.reply(wantedGenerator(parameters))

	def getAvailableTriggers(self):
		availableTriggers = []
		for generator, triggers in self.generators.iteritems():
			if isinstance(triggers, basestring):
				availableTriggers.append(triggers)
			else:
				availableTriggers.extend(triggers)
		return sorted(availableTriggers)

	def getRandomLine(self, filename, filelocation=None):
		if not filelocation:
			filelocation = self.filesLocation
		return SharedFunctions.getRandomLineFromFile(os.path.join(filelocation, filename))

	@staticmethod
	def numberToText(number):
		singleNumberNames = {0: u"zero", 1: u"one", 2: u"two", 3: u"three", 4: u"four", 5: u"five", 6: u"six", 7: u"seven",
							 8: u"eight", 9: u"nine", 10: u"ten", 11: u"eleven", 12: u"twelve", 13: u"thirteen",
							 14: u"fourteen", 15: u"fifteen", 16: u"sixteen", 17: u"seventeen", 18: u"eighteen", 19: u"nineteen"}
		if number in singleNumberNames:
			return singleNumberNames[number]
		else:
			#TODO: Handle numbers larger than 19 by combining words, like "twenty" and "two" for 22
			return unicode(number)

	@staticmethod
	def getBasicOrSpecialLetter(vowelOrConsonant, basicLetterChance):
		basicLetters = []
		specialLetters = []

		if isinstance(vowelOrConsonant, int):
			#Assume the provided argument is a chance percentage of vowel
			if random.randint(1, 100) <= vowelOrConsonant:
				vowelOrConsonant = "vowel"
			else:
				vowelOrConsonant = "consonant"

		if vowelOrConsonant == "vowel":
			basicLetters = ['a', 'e', 'i', 'o', 'u']
			specialLetters = ['y']
		else:
			basicLetters = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't']
			specialLetters = ['j', 'q', 'v', 'w', 'x', 'z']

		if random.randint(1, 100) <= basicLetterChance:
			return random.choice(basicLetters)
		else:
			return random.choice(specialLetters)


	@staticmethod
	def isGenderParameter(arg):
		return arg.lower() in ("f", "female", "woman", "girl", "m", "male", "man", "boy")

	@staticmethod
	def getGenderWords(genderString, allowUnspecified=True):
		if genderString is not None:
			genderString = genderString.lower()
		if not genderString or genderString == '':
			# No gender specified, pick one on our own
			roll = random.randint(1, 100)
			if allowUnspecified and roll <= 45 or roll <= 50:
				gender = "f"
			elif allowUnspecified and roll <= 90 or roll <= 100:
				gender = "m"
			else:
				gender = "misc"
		elif genderString in ("f", "female", "woman", "girl"):
			gender = "f"
		elif genderString in ("m", "male", "man", "boy"):
			gender = "m"
		elif allowUnspecified:
			gender = "misc"
		else:
			return False

		if gender == "f":
			return {"gender": "f", "genderNoun": "Woman", "genderNounYoung": "Girl", "pronoun": "she",
								 "possessivePronoun": "her", "personalPronoun": "her"}
		elif gender == "m":
			return {"gender": "m", "genderNoun": "Man", "genderNounYoung": "Boy", "pronoun": "he",
								 "possessivePronoun": "his", "personalPronoun": "him"}
		return {"gender": "misc", "genderNoun": "Person", "genderNounYoung": "Kid", "pronoun": "they",
								 "possessivePronoun": "their", "personalPronoun": "them"}


	def parseGrammarFile(self, grammarFilename, variableDict=None, parameters=None):
		if not variableDict:
			variableDict = {}

		#Load the file
		with open(os.path.join(self.filesLocation, grammarFilename), "r") as grammarfile:
			grammar = json.load(grammarfile)

		#First check if the starting field exists
		if '_start' not in grammar:
			return u"Error: No '_start' field found in '{}'!".format(grammarFilename)

		#Parse any options specified
		if '_options' in grammar:
			# Parse arguments
			if u'parseGender' in grammar['_options']:
				gender = ''
				for param in parameters:
					if self.isGenderParameter(param):
						gender = param
				variableDict.update(self.getGenderWords(gender))
			if u'generateName' in grammar['_options']:
				#If a gender was provided or requested, use that to generate a name
				if 'gender' in variableDict:
					variableDict['name'] = self.generateName([variableDict['gender']])
				#Otherwise have the function decide
				else:
					variableDict['name'] = self.generateName()
				nameparts = variableDict['name'].split(' ')
				variableDict['firstname'] = nameparts[0]
				variableDict['lastname'] = nameparts[-1]

		#Start the parsing!
		sentence = grammar["_start"]
		tagFinderPattern = re.compile(r"<(.+?[^/])>", re.UNICODE)
		argumentSplitterPattern = re.compile(r"(?<!/)\|", re.UNICODE)
		while True:
			tagmatch = tagFinderPattern.search(sentence)
			if not tagmatch:
				break
			field = tagmatch.group(1)
			replacement = u""

			#Special commands start with an underscore
			arguments = argumentSplitterPattern.split(field)
			fieldKey = arguments[0]
			if fieldKey.startswith(u"_"):
				if fieldKey == u"_randint" or fieldKey == u"_randintasword":
					value = random.randint(int(arguments[1]), int(arguments[2]))
					if fieldKey == u"_randint":
						replacement = unicode(value)
					elif fieldKey == u"_randintasword":
						replacement = self.numberToText(value)
				elif fieldKey == u"_file":
					#Load a sentence from the specified file. Useful for not cluttering up the grammar file with a lot of options
					newFilename = arguments[1]
					replacement = self.getRandomLine(newFilename)
				elif fieldKey == u"_setvar":
					#<_setvar|varname|value>
					variableDict[arguments[1]] = arguments[2]
				elif fieldKey == u"_remvar":
					if arguments[1] in variableDict:
						del variableDict[arguments[1]]
				elif fieldKey == u"_hasvar":
					#<_hasvar|varname|stringIfVarnameExists|stringIfVarnameDoesntExist>
					if arguments[1] in variableDict:
						replacement = arguments[2]
					else:
						replacement = arguments[3]
				elif fieldKey == u"_variable" or fieldKey == u"_var":
					#Variable, fill it in if it's in the variable dictionary
					if arguments[1] not in variableDict:
						return u"Error: Referenced undefined variable '{}' in field '{}'".format(arguments[1], field)
					else:
						replacement = variableDict[arguments[1]]
				elif fieldKey == u"_if":
					#<_if|varname=string|stringIfTrue|stringIfFalse>
					firstArgumentParts = arguments[1].split('=')
					if len(arguments) < 4:
						return u"Error: Not enough arguments in 'if' for field '{}'".format(field)
					if firstArgumentParts[0] not in variableDict:
						return u"Error: Referenced undefined variable '{}' in 'if' of field '{}'".format(firstArgumentParts[0], field)
					if variableDict[firstArgumentParts[0]] == firstArgumentParts[1]:
						replacement = arguments[2]
					else:
						replacement = arguments[3]
				elif fieldKey == u"_ifcontains":
					#<_ifcontains|string|substringToCheckFor|stringIfSubstringInString|stringIfSubstringNotInString>
					if len(arguments) != 5:
						return u"Error: Not enough parameters in 'ifcontains' of field '{}'. 5 fields required, found {}".format(field, len(arguments))
					if arguments[1] == u"_params":
						arguments[1] = " ".join(parameters).decode("utf-8", errors="replace")
					if arguments[2] in arguments[1]:
						replacement = arguments[3]
					else:
						replacement = arguments[4]
				elif fieldKey == u"_hasparameters" or fieldKey == u"_hasparams":
					#<_hasparams|stringIfHasParams|stringIfDoesntHaveParams>"
					#Checks if there are any parameters provided
					if parameters and len(parameters) > 0:
						replacement = arguments[1]
					else:
						replacement = arguments[2]
				elif fieldKey == u"_hasparameter" or fieldKey == u"_hasparam":
					#<_hasparam|paramToCheck|stringIfHasParam|stringIfDoesntHaveParam>
					#Used to check if the literal parameter was passed in the message calling this generator
					if arguments[1] in parameters:
						replacement = arguments[2]
					else:
						replacement = arguments[3]
				elif fieldKey == u"_params":
					#Fill in the provided parameter(s) in this field
					if not parameters:
						replacement = u""
					else:
						#The parameters will be strings. Convert them to unicode
						replacement = " ".join(parameters)
						replacement = replacement.decode("utf-8", errors="replace")
				elif fieldKey == u"_replace":
					# <_replace|string|whatToReplace|whatToReplaceItWith>
					if len(arguments) != 4:
						return u"Error: Not enough parameters for '_replace' in field '{}'. Need 4, found {}".format(field, len(arguments))
					replacement = arguments[1]
					if replacement == u"_params":
						replacement = " ".join(parameters).decode("utf-8", errors="replace")
					replacement = replacement.replace(arguments[2], arguments[3])
				elif fieldKey == u"_" or fieldKey == u"_dummy":
					replacement = u""
				else:
					return u"Error: Unknown command '{}' in field '{}' found!".format(fieldKey, field)
			#No command, so check if it's a valid key
			elif fieldKey not in grammar:
				return u"Error: Field '{}' not found in grammar file!".format(field)
			#All's well, fill it in
			else:
				if isinstance(grammar[fieldKey], list):
					#It's a list! Just pick a random entry
					replacement = random.choice(grammar[fieldKey])
				elif isinstance(grammar[fieldKey], dict):
					#Dictionary! The keys are chance percentages, the values are the replacement strings
					roll = random.randint(1, 100)
					for chance in sorted(grammar[fieldKey].keys()):
						if roll <= int(chance):
							replacement = grammar[fieldKey][chance]
							break
				elif isinstance(grammar[fieldKey], basestring):
					#If it's a string (either the string class or the unicode class), just dump it in
					replacement = grammar[fieldKey]
				else:
					return u"Error: No handling defined for type '{}' found in field '{}'".format(type(grammar[fieldKey]), fieldKey)

			#Process the possible arguments that can be provided
			for argument in arguments[1:]:
				if argument == 'lowercase':
					replacement = replacement.lower()
				elif argument == 'uppercase':
					replacement = replacement.upper()
				elif argument == 'camelcase' or argument == 'titlecase':
					replacement = replacement.title()
				elif argument == 'firstletteruppercase':
					if len(replacement) > 1:
						replacement = replacement[0].upper() + replacement[1:]
					else:
						replacement = replacement.upper()
				elif argument == 'bold':
					replacement = SharedFunctions.makeTextBold(replacement)

			#Sometimes decorations need to be passed on (like if we replace '<sentence|titlecase>' with '<word1> <word2>', 'word1' won't be titlecase)
			if len(arguments) > 1 and not fieldKey.startswith('_') and replacement.startswith('<'):
				closingBracketIndex = replacement.find('>')
				if closingBracketIndex > -1:
					orgReplacement = replacement
					replacement = replacement[:closingBracketIndex] + u"|" + u"|".join(arguments[1:]) + replacement[closingBracketIndex:]
					self.logDebug(u"[Gen] Replaced '{}' with '{}'".format(orgReplacement, replacement))

			#To allow for escaping < and > in <_if> for instance, remove one escape in the iteration so it does get parsed next round
			replacement = replacement.replace('/<', '<').replace('/>', '>').replace('/|', '|')

			sentence = sentence.replace(u"<{}>".format(field), replacement, 1).strip()
		#Exited from loop, return the fully filled-in sentence
		return sentence


	def generateName(self, parameters=None):
		genderDict = None
		namecount = 1
		#Determine if a specific gender name and/or number of names was requested
		if parameters and len(parameters) > 0:
			for param in parameters:
				if self.isGenderParameter(param):
					genderDict = self.getGenderWords(param, False)
				else:
					try:
						namecount = int(param)
						# Limit the number of names
						namecount = max(namecount, 1)
						namecount = min(namecount, 10)
					except ValueError:
						pass

		#If no gender parameter was passed, pick a random one
		if not genderDict:
			genderDict = self.getGenderWords(None, False)

		names = []
		for i in xrange(namecount):
			# First get a last name
			lastName = self.getRandomLine("LastNames.txt")
			#Get the right name for the provided gender
			if genderDict['gender'] == 'f':
				firstName = self.getRandomLine("FirstNamesFemale.txt")
			else:
				firstName = self.getRandomLine("FirstNamesMale.txt")

			#with a chance add a middle letter:
			if (parameters and "addletter" in parameters) or random.randint(1, 100) <= 15:
				names.append(u"{} {}. {}".format(firstName, self.getBasicOrSpecialLetter(50, 75).upper(), lastName))
			else:
				names.append(u"{} {}".format(firstName, lastName))

		return SharedFunctions.joinWithSeparator(names)


	def generateWord(self, parameters=None):
		"""Generate a word by putting letters together in semi-random order. Based on an old mIRC script of mine"""
		# Initial set-up
		vowels = ['a', 'e', 'i', 'o', 'u']
		specialVowels = ['y']

		consonants = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't']
		specialConsonants = ['j', 'q', 'v', 'w', 'x', 'z']

		newLetterFraction = 5
		vowelChance = 50  #percent

		#Determine how many words we're going to have to generate
		repeats = 1
		if parameters and len(parameters) > 0:
			repeats = SharedFunctions.parseInt(parameters[0], 1, 1, 25)

		words = []
		for i in xrange(0, repeats):
			word = u""
			currentVowelChance = vowelChance
			currentNewLetterFraction = newLetterFraction
			consonantCount = 0
			while random.randint(0, currentNewLetterFraction) <= 6:
				if random.randint(1, 100) <= currentVowelChance:
					consonantCount = 0
					#vowel. Check if we're going to add a special or normal vowel
					if random.randint(1, 100) <= 10:
						word += random.choice(specialVowels)
						currentVowelChance -= 30
					else:
						word += random.choice(vowels)
						currentVowelChance -= 20
				else:
					consonantCount += 1
					#consonant, same deal
					if random.randint(1, 100) <= 25:
						word += random.choice(specialConsonants)
						currentVowelChance += 30
					else:
						word += random.choice(consonants)
						currentVowelChance += 20
					if consonantCount > 3:
						currentVowelChance = 100
				currentNewLetterFraction += 1

			#Enough letters added. Finish up
			word = word[0].upper() + word[1:]
			words.append(word)

		#Enough words generated, let's return the result
		return u", ".join(words)

	def generateWord2(self, parameters=None):
		"""Another method to generate a word. Based on a slightly more advanced method, from an old project of mine that didn't go anywhere"""

		##Initial set-up
		#A syllable consists of an optional onset, a nucleus, and an optional coda
		#Sources:
		# http://en.wikipedia.org/wiki/English_phonology#Phonotactics
		# http://en.wiktionary.org/wiki/Appendix:English_pronunciation
		onsets = ["ch", "pl", "bl", "cl", "gl", "pr", "br", "tr", "dr", "cr", "gr", "tw", "dw", "qu", "pu",
				  "fl", "sl", "fr", "thr", "shr", "wh", "sw",
				  "sp", "st", "sk", "sm", "sn", "sph", "spl", "spr", "str", "scr", "squ", "sm"]  #Plus the normal consonants
		nuclei = ["ai", "ay", "ea", "ee", "y", "oa", "au", "oi", "oo", "ou"]  #Plus the normal vowels
		codas = ["ch", "lp", "lb", "lt", "ld", "lch", "lg", "lk", "rp", "rb", "rt", "rd", "rch", "rk", "lf", "lth",
				 "lsh", "rf", "rth", "rs", "rsh", "lm", "ln", "rm", "rn", "rl", "mp", "nt", "nd", "nch", "nk", "mph",
				 "mth", "nth", "ngth", "ft", "sp", "st", "sk", "fth", "pt", "ct", "kt", "pth", "ghth", "tz", "dth",
				 "ks", "lpt", "lfth", "ltz", "lst", "lct", "lx","rmth", "rpt", "rtz", "rst", "rct","mpt", "dth",
				 "nct", "nx", "xth", "xt"]  #Plus normal consonants

		simpleLetterChance = 65  #percent, whether a single letter is chosen instead of an onset/nucleus/coda
		basicLetterChance = 75  #percent, whether a simple consonant/vowel is chosen over  a more rare one

		#Prevent unnecessary and ugly code repetition

		#Start the word
		repeats = 1
		if parameters and len(parameters) > 0:
			repeats = SharedFunctions.parseInt(parameters[0], 1, 1, 25)

		words = []
		for i in xrange(0, repeats):
			syllableCount = 2
			if random.randint(1, 100) <= 50:
				syllableCount -= 1
			if random.randint(1, 100) <= 35:
				syllableCount += 1

			word = u""
			for j in range(0, syllableCount):
				#In most cases, add an onset
				if random.randint(1, 100) <= 75:
					if random.randint(1, 100) <= simpleLetterChance:
						word += self.getBasicOrSpecialLetter("consonant", basicLetterChance)
					else:
						word += random.choice(onsets)

				#Nucleus!
				if random.randint(1, 100) <= simpleLetterChance:
					word += self.getBasicOrSpecialLetter("vowel", basicLetterChance)
				else:
					word += random.choice(nuclei)

				#Add a coda in most cases (Always add it if this is the last syllable of the word and it'd be too short otherwise)
				if (j == syllableCount - 1 and len(word) < 3) or random.randint(1, 100) <= 75:
					if random.randint(1, 100) <= simpleLetterChance:
						word += self.getBasicOrSpecialLetter("consonant", basicLetterChance)
					else:
						word += random.choice(codas)

			word = word[0].upper() + word[1:]
			words.append(word)

		return u", ".join(words)

	def generateVideogame(self, parameters=None):
		repeats = 1
		replacementText = None
		if parameters and len(parameters) > 0:
			#Accepted parameters are either a number, which would be the game name repeats, or a word, which will replace a generated word later
			try:
				repeats = int(parameters[0])
				replacementWords = parameters[1:]
			except ValueError:
				replacementWords = parameters

			#Make the replacement text titlecase (But not with .title() because that also capitalizes "'s" at the end of words)
			replacementText = ""
			for word in replacementWords:
				if len(word) > 1:
					replacementText += word[0].upper() + word[1:] + " "
				else:
					replacementText += word.upper() + " "
			replacementText = replacementText.rstrip()
			#Game names are unicode, best make this unicode too
			replacementText = replacementText.decode("utf-8", errors="replace")

			#Clamp the repeats to a max of 5
			repeats = min(repeats, 5)
			repeats = max(repeats, 1)

		#Both data and functioning completely stolen from http://videogamena.me/
		gamenames = []
		for r in xrange(0, repeats):
			subjectsPicked = []
			gamenameparts = []
			for partFilename in ("FirstPart", "SecondPart", "ThirdPart"):
				repeatedSubjectFound = True
				while repeatedSubjectFound:
					repeatedSubjectFound = False
					word = SharedFunctions.getRandomLineFromFile(os.path.join(self.filesLocation, "VideogameName{}.txt".format(partFilename)))
					#Some words are followed by a subject list, to prevent repeats
					subjects = []
					if '^' in word:
						parts = word.split('^')
						word = parts[0]
						subjects = parts[1].split('|')
					#Check if the word has appeared in the name already, or is too similar in subject to an already picked word
					if word in gamenameparts or word in subjectsPicked:
						repeatedSubjectFound = True
						continue
					elif len(subjects) > 0:
						for subject in subjects:
							if subject in subjectsPicked:
								repeatedSubjectFound = True
								continue
						#If it's not a repeated subject, add the current subjects to the list
						subjectsPicked.extend(subjects)
					gamenameparts.append(word)

			gamename = u" ".join(gamenameparts)
			if replacementText and len(replacementText) > 0:
				#Replace a word with the provided replacement text
				#  (but not words like 'of' and 'the', so only words that start with upper-case)
				if replacementText.endswith("'s"):
					#Possessive, try to match it with an existing possessive
					words = re.findall(r"\w+'s?(?= )", gamename)
					if len(words) == 0:
						#No possessive words in the gamename, pick other words (but not the last one)
						words = re.findall(r"[A-Z]\w+(?= )", gamename)
				else:
					words = re.findall(r"[A-Z]\w+", gamename)
				gamename = gamename.replace(random.choice(words), replacementText, 1)
			gamenames.append(gamename)

		return SharedFunctions.joinWithSeparator(gamenames)
