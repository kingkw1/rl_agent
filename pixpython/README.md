# PixPython

Python code that connects to the Unreal pixel streaming signaling server. Provides audio and video from the Unreal viewport along with custom messages to send to Unreal. Messages can be keyboard and mouse input, queries for data from Unreal, or calling specific functions.

subsystemInterface.py defines the subsystem interface to handle data from the connection to Unreal with functions for when video, audio, or data is received. The built in messages that can send and receive data from Unreal is also here and includes an interface for creating new custom messages.

unrealConnect.py is the connection class that is for initiating the connection, handles the subsystems, and sends data to Unreal.

startingPoint.py provides sample subclasses for the subsystem interface to get specific functionality.