import os
import xml.etree.ElementTree as XML
from haversine import haversine as hsin
import haversine as hs
import math
import time
start = time.perf_counter()
#initialise directories
dir_path = "Output"
os.makedirs(dir_path, exist_ok=True)

with open('Navdata/Airports.txt', 'r') as f:
    Airports = f.readlines()

SIDptsymbol =  'SolidTriangle'
STARptsymbol = 'SolidStar'

def reciptrk(rwynum):
    opprwynum = rwynum + 18
    if opprwynum > 36:
        opprwynum -= 36
    return rwynum
    
def reciprwy(rwy_in):
    rwy_in = str(rwy_in).strip()  # ensure string

    # Extract numeric part
    rwynum_str = ''.join(filter(str.isdigit, rwy_in))
    rwynum = int(rwynum_str)

    # Calculate reciprocal runway number
    opprwynum = rwynum + 18
    if opprwynum > 36:
        opprwynum -= 36

    # Extract suffix
    suffix = rwy_in[-1] if rwy_in[-1] in 'LRC' else ''

    # Flip L ↔ R, keep C or '' as-is
    if suffix == 'L':
        oppsuffix = 'R'
    elif suffix == 'R':
        oppsuffix = 'L'
    else:
        oppsuffix = suffix

    return f"{opprwynum:02d}{oppsuffix}"

NAVAID_CACHE = None

def navaid(fix, ref_lat, ref_lon):
    global NAVAID_CACHE

    # Load navaids into cache once
    if NAVAID_CACHE is None:
        cache = {}
        with open('./Navdata/navaids.txt', 'r', encoding='utf-8') as f:
            for line in f:
                elem = line.split(',')

                # skip empty/broken lines
                if len(elem) < 8:
                    continue

                ident = elem[0].strip()
                lat = float(elem[6])
                lon = float(elem[7])

                cache.setdefault(ident, []).append((lat, lon))

        NAVAID_CACHE = cache

    ref_lat = float(ref_lat)
    ref_lon = float(ref_lon)
    ref_point = (ref_lat, ref_lon)

    best_dist = None
    best_point = None
    h = hsin

    # No matches → None
    candidates = NAVAID_CACHE.get(fix) 
    if not candidates:
        return None

    for lat, lon in candidates:
        d = h(ref_point, (lat, lon))
        if best_dist is None or d < best_dist:
            best_dist = d
            best_point = [lat, lon]

    return best_point

def drawall(ICAO):
    cache = ''
    SIDpoints = set()
    STARpoints = set()
    cachefile = []
 
    with open(f'Navdata/proc/{ICAO}.txt') as procs :
        procpoint = []
        proctype = 'invalid'
        for line in procs:
            elem = line.split(',')
            if not line.strip(): # Mark current set as 'done' when encountering a blank line.
                doneflag = 1 
            else:
                doneflag = 0

            if doneflag == 0:
                match elem[0]: #write SIDs and STAR data if the current set is not 'done'
                    case 'SID'|'STAR':
                        proctype = elem[0]
                        procname = elem[1]
                        procrwy = elem[2]
                    case 'DF'| 'TF'| 'CF'| 'IF': # write fixes
                        procpoint.append(elem[1])
                        if proctype == 'SID':
                            SIDpoints.add(elem[1])
                        elif proctype == 'STAR':
                            STARpoints.add(elem[1])                    
                    case 'AF': #write arc fixes
                        
                        fixcoord = navaid(elem[5],elem[2],elem[3])
                        startdir = float(elem[8])
                        dist     = float(elem[7])
                        endir    = float(elem[6])
                        
                        diff = (endir - startdir) % 360
                        if diff > 180:
                            diff -= 360    # pick shortest direction

                        step = 5 if diff > 0 else -5

                        bearing = startdir
                        points = []
                        target = abs(diff // 5)
                        count = 0

                        while count < target:

                            diff = endir-bearing
                            arcpoint = (hs.inverse_haversine(fixcoord, dist, math.radians(bearing), unit='nmi'))
                            lat = round(arcpoint[0],7)
                            lon = round(arcpoint[1],7)
                            procpoint.append(formatcoord(lat,lon))
                            count += 1
                            bearing += step
                        
                    case _: #edge case
                        if proctype == 'SID' or proctype == 'STAR':
                            proctype = proctype
                        else: 
                            proctype = 'invalid'
                        
            elif not line.strip(): #if empty line
                pointout = ''
                for p in procpoint:
                    pointout = pointout+p+'/'

                if proctype == 'invalid':
                    continue

                #write to cache
                cache = [proctype,procname,procrwy,pointout]
                cachefile.append(cache)
                #reset variables
                proctype = ''
                procname = ''
                procpoint = []
                proctype = 'invalid'
            else:
                pass
        for i in SIDpoints:
            cache = ['point',i,'SID']
            cachefile.append(cache)
        for i in STARpoints:
            cache = ['point',i,'STAR']
            cachefile.append(cache)
    return cachefile

def suicideDetect(ICAO,data,retrwy='False'):
    SIDrwys = []
    STARrwys = []
    out1 = []
    out0 = []
    rwylist = []
    for line in data: # this for loop parses the cache
        proctype = line[0]
        procrwy = line[2]
        if procrwy == 'ALL':
            if len(rwylist) <1:
                rwylist = lookup(ICAO)[3]
            for i in rwylist:
                if proctype == 'SID':
                    SIDrwys.append(i[0])
                elif proctype == 'STAR':
                    STARrwys.append(i[0])
                else:
                    pass
        elif proctype == 'SID' and procrwy not in SIDrwys:
            SIDrwys.append(procrwy)
        elif proctype == 'STAR' and procrwy not in STARrwys:
            STARrwys.append(procrwy)
    if retrwy == 'True':
        out1 = STARrwys
    else:
        out1 = ''

    if len(SIDrwys) > 2 or len(STARrwys) > 2:
        return ('False',out1)    


    if len(SIDrwys) == 1 and len(STARrwys) == 1:
        diff = int(SIDrwys[0])-18-int(STARrwys[0])
        if diff == 0:
            out0 = 'True'
        else:
            out0 = 'False'
    else:
        out0 = 'False'
    


    return (out0,out1)

def formatcoord(lat,lon):
    if float(lat) < 0:
        latsign = '-'
    else:
        latsign = '+'

    if float(lon) < 0:
        lonsign = '-'
    else:
        lonsign = '+'
    
    latsplit = (str(lat).lstrip('-')).split('.')
    lonsplit = (str(lon).lstrip('-')).split('.')

    latnum = int(latsplit[0])
    lonnum = int(lonsplit[0])

    lat2 = f'{latsign}{latnum:02d}.{latsplit[1]}'
    lon2 = f'{lonsign}{lonnum:03d}.{lonsplit[1]}'
    latlon = lat2+lon2
    return latlon

def writexml(ICAO, data, rwy, recip='False'): #rwy here should be the approach rwy

    plookup = lookup(ICAO)
    lat = str(plookup[1])
    lon = str(plookup[2])
    rrecip = reciprwy(rwy)
    rwy = str(rwy)
    Center = formatcoord(lat,lon)

    for i in plookup[3]:
        
        if i[0] == rwy.strip():
            lat1 = i[1] 
            lon1 = i[2]
            trk  = str(reciptrk(i[3]))
            latlon1 = formatcoord(lat1,lon1)
        if i[0] == rrecip.strip():
            lat2 = i[1]
            lon2 = i[2]
            trk  = str(reciptrk(i[3]))
            latlon2 = formatcoord(lat2,lon2)

    #XML Initialisation
    Maps = XML.Element('Maps')
    root = XML.SubElement(Maps, 'Map', {'Type':'System', 'Name':f'{ICAO}_RW{rwy}', 'Priority':'3', 'Center': f'{Center}' })
    
    Runway = XML.SubElement(root, 'Runway',{'Name':f'{rwy}'})
    Threshold1 = XML.SubElement(Runway, 'Threshold',{'Name':rwy, 'Position':latlon1, 'ExtendedCenterlineTrack': trk, 'ExtendedCentrelineLength':'12', 'ExtendedCentrelineWidth':'1', 'ExtendedCentrelineTickInterval':'1'})
    Threshold2 = XML.SubElement(Runway, 'Threshold',{'Name':rrecip, 'Position':latlon2})
    SIDsymbol = XML.SubElement(root, 'Symbol', {'Type': SIDptsymbol})
    STARsymbol = XML.SubElement(root, 'Symbol', {'Type': STARptsymbol})

    #XML Name Labels
    rootname = XML.SubElement(Maps, 'Map', {'Type':'System', 'Name':f'{ICAO}_RW{rwy}_NAMES', 'Priority':'3', 'Center': f'{Center}' })
    Label = XML.SubElement(rootname, 'Label')
    Labels = set()
    SIDpts = set()
    STARpts = set()
    if recip == 'True':
        rwy ='_recip'
        
    for line in data: # this for loop parses the cache
        proctype = line[0]
        procname = line[1]
        procrwy = line[2]
        try:
            points = line[3]
        except:
            pass
        pstyle = style(proctype)
        if (procrwy == rwy or procrwy == 'ALL' or recip == 'True') and (proctype == 'SID' or proctype == 'STAR'):
            root.append(XML.Comment(f"{proctype}: {procname}, RWY{procrwy}"))
            out = XML.SubElement(root, 'Line', {'Pattern':pstyle})
            pointlist = points.strip().rstrip('/')
            out.text = pointlist

            elem = pointlist.split('/')
            for i in elem:
                Labels.add(i)
                if proctype == 'SID':
                    SIDpts.add(i)
                elif proctype == 'STAR':
                    STARpts.add(i)
        
            
        '''
        elif proctype == 'point' and procrwy == 'SID': # this makes no fucking sense, but procrwy is also where the procedure info for the point is stored
            out = XML.SubElement(SIDsymbol,'Point') #make point
            out.text = procname.strip() 
            label = XML.SubElement(Label, 'Point') #make label
            label.text = procname.strip()

        elif proctype == 'point' and procrwy == 'STAR':
            out = XML.SubElement(STARsymbol,'Point')
            out.text = procname.strip()
            label = XML.SubElement(Label, 'Point')
            label.text = procname.strip()
        '''
    for i in STARpts:
        out = XML.SubElement(STARsymbol,'Point')
        out.text = i
    for i in SIDpts:
        out = XML.SubElement(SIDsymbol,'Point')
        out.text = i
    for i in Labels:
        out = XML.SubElement(Label, 'Point')
        out.text = i

    #XML end wrapping up and writing
    tree = XML.ElementTree(Maps)
    XML.indent(Maps, space="    ")
    tree.write(f"./output/{ICAO}_RW{rwy}.xml", encoding="utf-8", xml_declaration=True)

def style(ptype, sidpat ='Dotted', starpat ='Dashed'):
    if ptype == 'SID':
        return sidpat
    elif ptype == 'STAR':
        return starpat

def main(ICAO):
    '''
    for files in os.listdir('./cache'):
        os.remove('./cache/'+files)
        print('removed'+files)
    '''
    
    data = drawall(ICAO)
    rwydet = suicideDetect(ICAO, data, 'True')
    if rwydet[0] == 'False':
        for i in rwydet[1]:
            writexml(ICAO,data,f'{i}')
    else:
        writexml(ICAO,data,rwydet[1][0],'True')

def lookup(ICAO):
    with open('./Navdata/Airports.txt', 'r') as f:
        f.seek(0, 2)              # go to end of file
        file_size = f.tell()
        
        low = 0
        high = file_size
        
        while low < high:
            mid = (low + high) // 2
            f.seek(mid)
            # Move to the start of the next full line
            if mid != 0:
                f.readline()
            line = f.readline()
            if not line:
                high = mid
                continue
            
            line = line.strip()
            if not line or line[0] != 'A':
                # Skip non-airport lines by moving forward
                while True:
                    pos = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if line and line[0] == 'A':
                        break
                if not line:
                    break  # EOF
                        
            fields = line.split(",")
            icao = fields[1]
            if icao == ICAO:
                name = fields[2]
                lat = float(fields[3])
                lon = float(fields[4])
                
                # Collect subsequent runway lines with their positions
                runways = []
                while True:
                    pos = f.tell()
                    next_line = f.readline()
                    if not next_line:
                        break
                    next_line = next_line.strip()
                    if not next_line:
                        continue
                    if next_line[0] == 'A':  # next airport
                        break
                    if next_line[0] == 'R':  # runway line
                        r_fields = next_line.split(",")
                        # latitude is field 8, longitude is field 9
                        r_lat = float(r_fields[8])
                        r_lon = float(r_fields[9])
                        trk = int(r_fields[2])
                        runways.append(
                            [r_fields[1], r_lat ,r_lon,trk]
                        )
                
                return name, lat, lon, runways
            
            elif icao < ICAO:
                low = f.tell()  # go after this line
            else:
                high = mid      # search earlier portion
                
    return None

i = 0
while i < 2:
    main('EHAM')
    i += 1

end = time.perf_counter()

print("Execution time:", (end - start)*1000, "miliseconds")