import os
import xml.etree.ElementTree as XML



#initialise directories
dir_path = "Output"
os.makedirs(dir_path, exist_ok=True)

with open('Navdata/Airports.txt', 'r') as f:
    Airports = f.readlines()

Maps = XML.Element('Maps')

def reciprwy(rwy_in):
    rwy_in = str(rwy_in)
    rwynum = int(rwy_in.rstrip('LRC'))


    opprwynum = rwynum+18
    if opprwynum > 36:
        opprwynum = opprwynum-36

    suffix_map = {
    "L": "R",
    "R": "L",
    "C": "C"
    }
    oppsuffix = suffix_map.get(rwy_in, "") #gets opposite rwy suffix

    return f"{opprwynum:02d}{oppsuffix}"

def drawall(ICAO,SID_Pattern='Dotted',STAR_Pattern='Dashed'):
    all = []
    root = XML.SubElement(Maps,'map')
    with open (f'Navdata/proc/{ICAO}.txt') as procs:
        procpoint = []
        proctype = 'invalid'
        for line in procs:
            elem = line.split(',')
            if not line.strip():
                doneflag = 1
                
            else:
                doneflag = 0

            if doneflag == 0:
                match elem[0]:
                    case 'SID'|'STAR':
                        proctype = elem[0]
                        procname = elem[1]
                        procrwy = elem[2]
                    case 'VA'| 'DF'| 'TF'| 'CF'| 'IF':
                        procpoint.append(elem[1])
                    case 'AF':
                        pass
                        #drawarc
                    case _:
                        if proctype == 'SID' or proctype == 'STAR':
                            proctype = proctype
                        else: 
                            proctype = 'invalid'
                    
            elif not line.strip():
                pointout = ''
                for p in procpoint:
                    pointout = pointout+p+'/'

                match proctype: #styling and also prevent non-sid/star lines from being drawn
                    case 'SID':
                        pattern = SID_Pattern  
                    case 'STAR':
                        pattern = STAR_Pattern
                    case 'invalid':
                        continue

                #write to ET
                root.append(XML.Comment(f'{proctype}:{procname} RWY{procrwy}'))
                procml = XML.SubElement(root, 'Line', {"Pattern": pattern})
                procml.text = pointout


                #reset variables
                proctype = ''
                procname = ''
                procpoint = []
                proctype = 'invalid'
            else:
                pass
    ### Cache XML handler:
    tree = XML.ElementTree(root)
    #deleter(root)
    XML.indent(root, space="    ")
    tree.write(f"./cache/{ICAO}.xml", encoding="utf-8", xml_declaration=True)

#def suicideDetect():


drawall('WALL')

