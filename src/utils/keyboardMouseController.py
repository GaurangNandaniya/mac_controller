from pynput import keyboard,mouse
import pyttsx3
from threading import Thread

#for keyboard locking
keyboard_listener = None
lock_keys = False

mouse_listener = None


# Initialize the pyttsx3 engine once
engine = pyttsx3.init() 
engine.setProperty('voice', 'com.apple.voice.compact.en-AU.Karen')  # Set to "Karen" voice
engine.setProperty('rate', 100)  # Set speech rate (words per minute)

def speak_text(text):
    """Function to perform text-to-speech in a separate thread."""
    engine.say(text)
    engine.runAndWait()

def text_to_speech(text):
    try:
        # Create and start a new thread for the speech task
        speech_thread = Thread(target=speak_text, args=(text,))
        speech_thread.start()
    except Exception as e:
        print(f"Error in text-to-speech conversion: {e}")

def on_press(key):
    print(f"Key pressed: {key}")
    # if lock_keys:
    #     # Swallow all key presses
    #     return False


def lock_keyboard():
    global keyboard_listener
    if keyboard_listener is None:
        keyboard_listener = keyboard.Listener(on_press=on_press, suppress=True)
        keyboard_listener.start()
        text_to_speech("Keyboard is disabled.")

def unlock_keyboard():
    global keyboard_listener

    if keyboard_listener is not None:
        print("keyboard_listener stopped.")
        text_to_speech("Keyboard is enabled.")
        keyboard_listener.stop()
        keyboard_listener = None


def on_move(x, y):
    print(f"Mouse moved to: {x}, {y}")
    # return False  # block move

def on_click(x, y, button, pressed):
    print(f"Mouse clicked at: {x}, {y} with {button}, pressed: {pressed}")
    # return False  # block clicks

def on_scroll(x, y, dx, dy):
    print(f"Mouse scrolled at: {x}, {y} with delta: {dx}, {dy}")
    # return False  # block scroll


def lock_mouse():
    global mouse_listener
    if mouse_listener is None:
        mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll, suppress=True)
        mouse_listener.start()
        text_to_speech("Mouse is disabled.")

def unlock_mouse():
    global mouse_listener

    if mouse_listener is not None:
        print("mouse_listener stopped.")
        text_to_speech("Mouse is enabled.")
        mouse_listener.stop()
        mouse_listener = None



