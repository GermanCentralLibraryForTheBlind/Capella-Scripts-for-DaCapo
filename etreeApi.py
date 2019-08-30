# -*- coding: utf-8 -*-
""" capellaScript -- (c) DZB Leipzig, Martin Müller
>>> etree API for capx files
<<<
"""
from xml.etree import ElementTree as ET
from fractions import Fraction
from math import log
from collections import OrderedDict
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
import os
import zipfile
import tempfile

# capxml namespace

def updateZip(zipname, filename, data):
    # Update a file in a zip
    # generate a temp file
    tmpfd, tmpname = tempfile.mkstemp(dir=os.path.dirname(zipname))
    os.close(tmpfd)

    # create a temp copy of the archive without filename            
    with zipfile.ZipFile(zipname, 'r') as zin:
        with zipfile.ZipFile(tmpname, 'w') as zout:
            zout.comment = zin.comment # preserve the comment
            for item in zin.infolist():
                if item.filename != filename:
                    zout.writestr(item, zin.read(item.filename))

    # replace with the temp archive
    os.remove(zipname)
    os.rename(tmpname, zipname)

    # now add filename with its new data
    with zipfile.ZipFile(zipname, mode='a', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, data)

class Part(object):
    """
    A Part here is a part in a sense of the sum of all staffs identified by a staffLayout in the score header, e.g. Piano right hand (not the whole piano)
    @param name: identifier as in <staffLayout description=""> in the header
    @param staves: list of "staff" elements (staff = one line of a part in Capella)
        collected from
        <systems>
            <system>
                <staves>
                    <staff layout="name">
    """
    def __init__(self, number, name, staves, brackets):
        self.number = number
        self.name = name
        self.staves = staves
        self.brackets = brackets
        self._voices = None

    def voice_durations(self):
        return [sum([line.duration for line in voice]) for voice in self.voices]

    def duration(self):
        pass

    @property
    def voices(self):
        """
        returns list of voices, 
          each containing a list of Voice objects, one for each system line of the part
        """
        if self._voices is None:
            voices = []
            line_length = 0
            position = 0
            # one staff = one line in part
            for staff_nr, staff in self.staves.items():
                #start position of a voice line measured from beginning
                position = position + line_length
                line_length = Fraction(0)
                defaultTime = staff.get('defaultTime')
                assert defaultTime is not None, "Attribut defaultTime nicht gesetzt in System Nummer:" + str(staff_nr)
                for voice_nr, staff_voice in enumerate(staff.findall('voices/voice')):
                    voice = Voice(self.number, staff_nr, voice_nr, staff_voice, position, defaultTime)
                    # length of line = longest voice in line
                    if voice.duration > line_length:
                        line_length = voice.duration
                    #print(voice_nr, voice_duration(staff_voice))
                    if voice_nr+1 > len(voices):
                        voices.append([voice])
                    else:
                        voices[voice_nr].append(voice)
            self._voices = voices                    
        return self._voices            
    
    def __repr__(self):
        return '<Part:{}>'.format(self.name)


class Event(object):
    @property
    def duration(self):
        pass

    @property
    def noDuration(self):    
        if self.el is not None:
            d = self.el.find('.//duration')
            if d is not None:
                if d.get('noDuration') == 'true':
                    return True
        return False        
            
    def dotted_value(self, duration, dots):
        return duration + sum([duration/ 2**dot for dot in range(1,int(dots)+1)])    
    
    def find(self,tag_name):
        return self.el.find(tag_name)
    
    def findall(self,tag_name):
        return self.el.findall(tag_name)    

class Voice(object):
    def __init__(self, part_nr, staff_nr, voice_nr, el, position, defaultTime):
        self.el = el
        self.position = position
        self.defaultTime = defaultTime
        self.part_nr = part_nr
        self.staff_nr = staff_nr
        self.voice_nr = voice_nr
        self._noteObjs = None

    def __repr__(self):
        return 'Z{} Start:{}, Laenge:{}'.format(self.staff_nr,self.position, self.duration)

    # def timeSignAt(self, time=Fraction(0)):
    #     """find last timeSign before or at time"""
    #     timeSigns = self.timeSigns.reverse()
    #     for timeSign in timeSigns:
    #         if Fraction(timeSign.get('time')) <= self.position:
    #             return Fraction(timeSign.get('time'))
    #     return self.defaultTime        



    def noteObjs(self):
        timeSign = self.defaultTime

        if self._noteObjs is None:
            noteObjs = []
            position = 0
            events = self.el.find('noteObjects')
            for note_index, e in enumerate(events):
                if e.tag == 'timeSign':
                    timeSign =  e.get('time')
                noteObj = NoteObject(note_index, e, position, timeSign) #self.timeSignAt(position)
                noteObjs.append(noteObj)
                if noteObj.noDuration is not True:
                    position+= noteObj.duration
            self._noteObjs = noteObjs        
        return self._noteObjs       

    def events(self):
        events = []
        for event in self.noteObjs():
            if event.type in ['chord','rest']: events.append(event)
        return events    

    def notes(self):
        notes = []
        for event in self.noteObjs():
            if event.type == 'chord': notes.append(event)
        return notes    

    @property
    def timeSigns(self):
        timeSigns = []
        for event in self.noteObjs():
            if event.type == 'timeSign': timeSigns.append(event)
        return timeSigns    
        

    @property           
    def textObjects(self):
        textObjects = []
        for noteObj in self.noteObjs():
            textObjects.extend(noteObj.textObjects) 
        return textObjects    
   
    @property
    def duration(self):
        """returns sum of all contained duration elements
        """
        if self.el is not None:
            duration = 0
            for event in self.events():
                if event.noDuration is not True:
                    duration+= event.duration
        return duration           

    def lyrics(self, number=None):
        """returns all "verse elements"
        """
        path = './/lyric/verse'
        if number is not None:
            path = path + '[@i="' + str(number) + '"]'
        return self.el.findall(path)

    def lyrics_text(self, number=None):
        t = ''
        for vers in self.lyrics(number):
            if vers.text != None:
                t+= vers.text 
            if vers.get('hyphen')=='true':
                t+='-'
            else:
                t+=' '
        return t                        



class NoteObject(Event):
    """
    noteObj in Capella sense
    @param index postion in the list of noteObjs of the voice
    @param position in the voice (line)
    clefSign | timeSign | barline  |chord | rest
    """
    def __init__(self, index, el, position, timeSign=Fraction('4/4')):
        self.el = el
        self.position = position
        self.timeSign = timeSign
        self.type = self.el.tag
        self.index = index
        self._drawObjects = None

    def timeSign_to_meter(self, timeSign):
        namedtimeSigns = {'allaBreve':'2/2','longAllaBreve':'4/2','C':'4/4','infinite':'999/4'}
        if timeSign in namedtimeSigns:
            return Fraction(namedtimeSigns[timeSign])
        return Fraction(timeSign)

    @property
    def duration(self):
        """returns Fraction()
        """
        if self.el is not None:
            d = self.el.find('.//duration')
            if d is not None:
                base = Fraction(d.attrib['base'])
                dur = self.dotted_value(base, d.get('dots','0'))
                tuplet = d.find('tuplet')
                if tuplet is not None:
                    count = int(tuplet.get('count',2))
                    # http://www.capella.de/CapXML/CapXML-3.0.3.html#Tuplet
                    tripartite = tuplet.get('tripartite') == 'true'
                    prolong = tuplet.get('prolong') == 'true'
                    #smallest number greater than count, which equals (three times if tripartite) a power of two
                    if prolong: a = 1
                    #greatest number less than count, which equals (three times) a power of two
                    else: a = -1
                    z = count + a
                    f=1
                    if tripartite:
                        f=3
                    while not log(z/f,2).is_integer():
                        z+=a
                    dur = dur * Fraction(z, count)
                if self.type == 'rest':
                    display = self.el.find('.//display')
                    if display is not None:
                        if display.get('churchStyle','false') == 'true':
                            dur = dur * self.timeSign_to_meter(self.timeSign)

                return dur    
        return 0       

    def pitches(self):
        pitches = []
        for h in self.el.findall('heads/head'):
            pitch = dict({'name': h.attrib['pitch']})
            if h.find('alter') is not None:
                pitch['alter'] = h.find('alter').get('step',0)
            pitches.append(pitch)
        return pitches    

    @property
    def textObjects(self):
        tos = []
        for drawObj in self.drawObjects:
            if drawObj.find('text') is not None:
                to = TextObject(self, drawObj)
                if to.type == 'text':
                    tos.append(to)
        return tos        
    
    @property
    def drawObjects(self):
        if self._drawObjects is None:
            self._drawObjects = self.findall('drawObjects/drawObj')
        return self._drawObjects    

    def __repr__(self):
        pitches = ','.join([p['name']+p.get('alter','') for p in self.pitches()])
        return '{}'.format(pitches)

class TextObject(object):
    def __init__(self, noteObject, drawObj):
        self.noteObject = noteObject
        self.drawObj = drawObj
        self.font = None
        self.el = None
        self.type = 'text'
        self.text = ''
        if self.drawObj is not None:
            self.el = self.drawObj.find('text')
        if self.get_text():
            if self.el.find('font') is not None:
                self.font = self.el.find('font').attrib['face']
        if self.font is not None and self.font == "capella3":
            self.type = 'symbol'
                       
    
    def get_text(self):
        if self.el:
            if self.type == 'richText':
                pass
                # c = Rtf2Txt.getTxt(self.d['data']).strip()
            else:
                self.text = self.el.findtext('content').strip()
        return self.text


    def set_text(self, new_text):
        self.text = new_text
        if self.el is not None:
            self.el.find('content').text = new_text
        return self.text    
    
    def delete(self):
        if self.noteObject is not None and self.drawObj is not None:
            return self.noteObject.el.find('drawObjects').remove(self.drawObj)
        
    def __repr__(self):
        return self.text        

    def __eq__(self, other):
        if isinstance(other, TextObject):
            return (self.text == other.text)
        else:
            return False
    #hash needed for comparison of set() 's of text objects
    def __hash__(self):
        return hash(self.text)    

class HodderTag(TextObject):
    """
    Attributes:
        tag (str): identifier in upper case i.e. "P", "S" , "FN", "TITLE" etc.
        text (str): text value, i.e. page number or title of the score
        noteObj (capx.noteObj): note object in the current document
        drawObjNr (int): index of the drawObj in the noteObj
    """
    def __init__(self, tag_content, noteObject=None, drawObj=None):
        """
        Args:
            tag_content: Tag text without {}
        """ 
        self.startTag='{'
        self.endTag='}'
        super().__init__(noteObject, drawObj)

        self.content = tag_content
        # parts = self.content.split(':')
        col_pos = self.content.find(':')
        if col_pos>-1:
            self.tag = self.content[0:col_pos]
            self.value = self.content[col_pos+1:]
        else:
            self.tag = self.content
            self.value=''    
        self.noteObj =  noteObj
        self.drawObjNr = drawObjNr


    
    def set_text(self):
        new_text = self.startTag
        if self.tag>'':
             new_text+= self.tag+ ':'
        new_text+= self.value + self.endTag
        return super().set_text(new_text)

    # @staticmethod
    # def create_draw_obj(tag, text, font=dict(color=Color.RGB(153,50,0))):
    #     return dict(
    #             type='text',
    #             x=0, y=-4,
    #             font = font,
    #             align="left",
    #             content= '{' + tag + ':' + text + '}'
    #             ) 

    def set_value(self, new_value):
        self.value = new_value
        self.set_text()

    def set_tag(self, new_tag):
        self.tag = new_tag
        self.set_text()
        



class CapxScore(object):
    """Use class method CapxScore.read(filename) to instantiate from file
    """
    NS = 'http://www.capella.de/CapXML/2.0'

    def __init__(self, **kwargs):
        self.el = kwargs.get('el')
        self.zip_file_path = kwargs.get('zip_file_path')    
        self.xml_file = kwargs.get('xml_file')
        if self.el is not None:
            self.layout_el = self.find('layout')
        self._parts = None    
        # super(Gallery, self).__init__()

    @staticmethod
    def fromstring(xml):
        """
        Returns:
            root ET element from string without namespaces
        https://stackoverflow.com/questions/13412496/python-elementtree-module-how-to-ignore-the-namespace-of-xml-files-to-locate-ma
        Replacement for ET.fromstring(xml)
        """
        parser = ET.XMLParser(encoding="utf-8")
        it = ET.iterparse(StringIO(xml), parser=parser)
        for _, el in it:
            if '}' in el.tag:
                el.tag = el.tag.split('}', 1)[1]  # strip all namespaces
        return it.root
        
    @classmethod
    def read(cls,zip_file_path,xml_file='score.xml'):
        if zip_file_path:
            zip_file = zipfile.ZipFile(zip_file_path, mode='r')
            xml = zip_file.read(xml_file)
            root = cls.fromstring(xml.decode())
        zip_file.close()    
        return cls(el=root, zip_file_path=zip_file_path, xml_file=xml_file)    
    
    def find(self,tag_name):
        return self.el.find(tag_name)
    
    def findall(self,tag_name):
        return self.el.findall(tag_name)
    
    def write(self):
        self.el.set('xmlns',self.NS)
        xml = ET.tostring(self.el, encoding='utf8')
        updateZip(self.zip_file_path,'score.xml',xml)
        # d(xml)

    def voiceList(self):
        """
        List of part descriptions used for identifying parts in a System (= one line)
        <staff layout="unbenannt">
        """
        layout_el = self.el.find('layout')
        return [voiceDescription.attrib['description'] for voiceDescription in layout_el.findall('staves/staffLayout')]
        
    def parts(self):
        """
        returns: list of Part objects,
                 names '<layout><staffLayout description>'' attrib. 
        """
        if self._parts is None:
            parts = []
            for part_nr, layout_description in enumerate(self.voiceList()):
                brackets_from = self.layout_el.findall('.//brackets/bracket[@from="' + str(part_nr) + '"]')
                brackets_to = self.layout_el.findall('.//brackets/bracket[@to="' + str(part_nr) + '"]')
                
                systems = [system for system in self.el.iterfind('systems/system')]
                staves = {}
                for sys_nr, sys in enumerate(systems):
                    for staff in sys.iterfind(".//staff[@layout='" + layout_description + "']"):
                        staves[int(sys_nr)] = staff
                    staves = OrderedDict(sorted(staves.items(),key=lambda t: t[0]))    
                parts.append(Part(part_nr, layout_description, staves, {'from':brackets_from,'to':brackets_to}))
            self._parts = parts
        return self._parts    

    def brackets(self):
        if self.layout_el is not None:
            return self.layout_el.findall('brackets/bracket')
        return None

    def systems(self):
        for system in self.el.iterfind('systems/system'):
            yield system
    
    def staves(self):
        for sys in self.systems():
            yield sys.iterfind('staves/staff')
    
    def voices(self):
        for staff in self.staves(): 
            yield staff.iterfind('voice')
                
    def noteObjs(self):
        for sys in self.systems():
            for o in sys.noteObjs():
                yield o
    def heads(self):
        for sys in self.systems():
            for h in sys.heads():
                yield h    
    def add_gallery(self, gallery_el):
        gallery = self.find('gallery')
        if gallery is None:
            self.el.append(gallery_el)
        else:
            for drawObj in gallery_el:
                # do not double items
                if ET.tostring(drawObj) not in [ET.tostring(d) for d in gallery]:
                    gallery.append(drawObj)



class CapxGalleryFile(CapxScore):
    NS = 'http://www.capella.de/CagXML/3.0'
    # def __init__(self, **kwargs):
    #         super().__init__(**kwargs)

    @classmethod
    def read(cls,zip_file_path):
        return super(CapxGalleryFile, cls).read(zip_file_path,xml_file='cagx.xml')
    

# ET.register_namespace('', 'http://www.capella.de/CapXML/2.0')
# ET.register_namespace('', 'http://www.capella.de/CagXML/3.0')
