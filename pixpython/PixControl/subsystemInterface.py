from abc import ABC, abstractmethod
from typing import List, Tuple
import numpy as np

#interface for making subsystems that can receive data, audio video frames 
class SubsystemInterface(ABC):
    def __init__(self):
        self.ueClient = None

    @abstractmethod
    def initialize(self, client):
        self.ueClient = client

    def deInitialize(self):
        pass

    @abstractmethod
    def onVideo(self, frame: Tuple[np.ndarray, float]) -> None:
        pass

    @abstractmethod
    def onAudio(self, frame) -> None:
        pass

    @abstractmethod
    def onData(self, data: dict) -> None:
        pass

### outgoing message classes ###
#interface for the message commands that correspond to the message classes in Unreal
class UERequestDataInterface(ABC):
    def __init__(self):
        self.callback = False
        self.messageID = None
        self.bRunonServer = False
        self.agentID = 0

    def formData(self) -> dict:
        msgDict = dict()
        msgDict['dataType'] = type(self).__name__
        msgDict['data'] = self.__dict__
        return msgDict

class Transform(UERequestDataInterface):
    def __init__(self, agentID: int):
        super().__init__()
        self.agentID = agentID
        
class Raycast(UERequestDataInterface):
    def __init__(self, agentID: int):
        super().__init__()
        self.agentID = agentID

class ConsoleCommand(UERequestDataInterface):
    def __init__(self, command: str):
        super().__init__()
        self.commandString = command

class PixResolution(UERequestDataInterface):
    def __init__(self, width: int, height: int):
        super().__init__()
        self.commandString = 'PixelStreaming.Encoder.TargetSize ' + str(width) + 'x' + str(height)

class CallFunction(UERequestDataInterface):
    def __init__(self, runOnServer: bool, agentID: int, functionName: str, *parameters: str):
        super().__init__()
        #determines if the function should be run on server or client
        self.bRunonServer = runOnServer
        self.functionString = functionName
        self.agentID = agentID
        for item in parameters:
            self.functionString += ' ' + item  

class GetWorld(UERequestDataInterface):
    def __init__(self):
        super().__init__()

class LocalID(UERequestDataInterface):
    def __init__(self):
        super().__init__()


### incoming message parsing classes ###
#interface for parsing the responce messages from Unreal
class InMessageInterface(ABC):
    def __init__():
        pass
    
    @classmethod
    @abstractmethod
    def loadMessage(cls, data: dict) -> 'InMessageInterface':
        pass

    @classmethod
    @abstractmethod
    def getMessageType(cls) ->str:
        pass

class WorldData(InMessageInterface):
    def __init__(self):
        self.agents = []

    @classmethod
    def loadMessage(cls, data: dict) -> InMessageInterface:
        tt = WorldData()
        tt.agents = data['agents']
        return tt

    @classmethod
    def getMessageType(cls) -> str:
        return 'WorldLVR'

    #agent accessor functions
    def getAgentLocationByID(self, agentID: int) -> Tuple[float, float, float]:
        for agent in self.agents:
            if agent['agentId'] == agentID:
                agentl = agent['location']
                return (float(agentl['x']), float(agentl['y']), float(agentl['z']))
        
        return None

    def getAgentRotatioByID(self, agentID: int) -> Tuple[float, float, float]:
        for agent in self.agents:
            if agent['agentId'] == agentID:
                agentr = agent['rotation']
                return (float(agentr['x']), float(agentr['y']), float(agentr['z']))
        
        return None

    def getAgentVelocityByID(self, agentID: int) -> Tuple[float, float, float]:
        for agent in self.agents:
            if agent['agentId'] == agentID:
                agentv = agent['velocity']
                return (float(agentv['x']), float(agentv['y']), float(agentv['z']))

        return None

    def getAgentNameByID(self, agentID: int) -> str:
        for agent in self.agents:
            if agent['agentId'] == agentID:
                return agent['agentName']

        return ''

    def getAllAgentID(self) -> List[int]:
        result = []
        for agent in self.agents:
            result.append(int(agent['agentId']))

        return result

class RaycastData(InMessageInterface):
    def __init__(self):
        self.hit = False
        self.location = ()
        self.hitActorName = ''

    @classmethod
    def loadMessage(cls, data: dict) -> InMessageInterface:
        tt = RaycastData()
        tt.hit = bool(data['hit'])
        tt.hitActorName = data['hitActorName']
        hitl = data['location']
        tt.location = (float(hitl['x']), float(hitl['y']), float(hitl['z']))
        return tt

    @classmethod
    def getMessageType(cls) -> str:
        return 'Raycast'

class TransformData(InMessageInterface):
    def __init__(self):
        self.location = ()
        self.rotation = ()
        self.velocity = ()
        self.agentID = 0
        self.agentName = ''

    @classmethod
    def loadMessage(cls, data: dict) -> InMessageInterface:
        tt = TransformData()
        tt.agentID = int(data['agentId'])
        tt.agentName = data['agentName']
        tloc = data['location']
        trot = data['rotation']
        tvel = data['velocity']
        tt.location = (float(tloc['x']), float(tloc['y']), float(tloc['z']))
        tt.rotation = (float(trot['x']), float(trot['y']), float(trot['z']))
        tt.velocity = (float(tvel['x']), float(tvel['y']), float(tvel['z']))
        return tt

    @classmethod
    def getMessageType(cls) -> str:
        return 'Transform'

class LocalIDData(InMessageInterface):
    def __init__(self):
        self.agentID = 0

    @classmethod
    def loadMessage(cls, data: dict) -> InMessageInterface:
        tt = LocalIDData()
        tt.agentID = data["agentId"]
        return tt
    
    @classmethod
    def getMessageType(cls) -> str:
        return 'LocalID'