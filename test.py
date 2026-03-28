import pyttsx3

engine = pyttsx3.init()
voices = engine.getProperty('voices')
print("Number of voices:",len(voices))
rate = engine.getProperty('rate')
print("rate:", rate)
engine.setProperty('rate', rate-50)
engine.setProperty('volume', 1.0)  # Set volume (0.0 to 1.0)
engine.say('The quick brown fox jumped over the lazy dog.')
# engine.runAndWait()
#filter female voices
voices = [voice for voice in voices if 'female' in voice.gender.lower()]

print("Filtered female voices:", len(voices))

for voice in voices:
    print("Voice:")
    print("ID: %s" % voice.id)
    print("Name: %s" % voice.name)
    print("Languages: %s" % voice.languages)
    print("Gender: %s" % voice.gender)
    print("Age: %s" % voice.age)
    engine.setProperty('voice', voice.id)
    engine.say(f'The quick brown fox jumped over the lazy dog. This was spoken using the voice {voice.name}')
engine.runAndWait()

#selected voice 
# "Karen" - com.apple.voice.compact.en-AU.Karen