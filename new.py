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
    APPpoints = set()
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
                    case 'SID'|'STAR'| 'APPTR':
                        proctype = elem[0]
                        procname = elem[1]
                        procrwy = elem[2]
                    case 'DF'| 'TF'| 'CF'| 'IF': # write fixes
                        procpoint.append(elem[1])
                        if proctype == 'SID':
                            SIDpoints.add(elem[1])
                        elif proctype == 'STAR':
                            STARpoints.add(elem[1]) 
                        elif proctype == 'APPTR':
                            APPpoints.add(elem[1])                   
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
                        if proctype == 'SID' or proctype == 'STAR' or proctype == 'APPTR':
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
                
        # for i in SIDpoints:
        #     cache = ['point',i,'SID']
        #     cachefile.append(cache)
        # for i in STARpoints:
        #     cache = ['point',i,'STAR']
        #     cachefile.append(cache)             
        # for i in APPpoints:
        #     cache = ['point',i,'APPTR']
        #     cachefile.append(cache)
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
                rwylist = lookup(ICAO)['rwys']
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

def writexml(ICAO, data, rwy, printAPPTR = False, recip='False'): #rwy here should be the approach rwy

    plookup = lookup(ICAO)
    lat = str(plookup['lat'])
    lon = str(plookup['lon'])
    Center = formatcoord(lat,lon)
    rwy = str(rwy)
    rrecip = reciprwy(rwy)

    for i in plookup['rwys']: #look for threshold coords
        
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
    SIDMAP   = XML.SubElement(Maps, 'Map', {'Type':'System', 'Name':f'{ICAO}_RW{rwy}_SID', 'Priority':'3', 'Center': f'{Center}' })
    STARMAP  = XML.SubElement(Maps, 'Map', {'Type':'System', 'Name':f'{ICAO}_RW{rwy}_STAR', 'Priority':'3', 'Center': f'{Center}' })
    APPTRMAP = XML.SubElement(Maps, 'Map', {'Type':'System', 'Name':f'{ICAO}_RW{rwy}_APPTR', 'Priority':'3', 'Center': f'{Center}' })    
    
    STARrwy = XML.SubElement(STARMAP, 'Runway',{'Name':f'{rwy}'})
    if str(rwy).lower != 'all': 
        STARthresh1 = XML.SubElement(STARrwy, 'Threshold',{'Name':rwy, 'Position':latlon1, 'ExtendedCenterlineTrack': trk, 'ExtendedCentrelineLength':'12', 'ExtendedCentrelineWidth':'1', 'ExtendedCentrelineTickInterval':'1'})
        STARthresh2= XML.SubElement(STARrwy, 'Threshold',{'Name':rrecip, 'Position':latlon2})

    SIDsymbol  = XML.SubElement(SIDMAP, 'Symbol', {'Type': SIDptsymbol})
    STARsymbol = XML.SubElement(STARMAP, 'Symbol', {'Type': STARptsymbol})
    APPTRsymbol = XML.SubElement(APPTRMAP, 'Symbol', {'Type': STARptsymbol})

    #XML Name Labels
    SIDLabelmap = XML.SubElement(Maps, 'Map', {'Type':'System', 'Name':f'{ICAO}_RW{rwy}_SID_Labels', 'Priority':'3', 'Center': f'{Center}' })
    STARLabelmap = XML.SubElement(Maps, 'Map', {'Type':'System', 'Name':f'{ICAO}_RW{rwy}_STAR_Labels', 'Priority':'3', 'Center': f'{Center}' })
    APPLabelmap = XML.SubElement(Maps, 'Map', {'Type':'System', 'Name':f'{ICAO}_RW{rwy}_APP_Labels', 'Priority':'3', 'Center': f'{Center}' })
    
    SIDLabels  = XML.SubElement(SIDLabelmap,'Label')
    STARLabels = XML.SubElement(STARLabelmap,'Label')
    APPLabels = XML.SubElement(STARLabelmap,'Label')
    
    SIDLabel   = set()
    STARLabel  = set()
    APPTRLabel = set()
    SIDpts   = set()
    STARpts  = set()
    APPpts   = set()
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
        if procrwy == rwy or procrwy == 'ALL':
            if proctype == 'SID':
                SIDMAP.append(XML.Comment(f'{procname}'))
                out = XML.SubElement(SIDMAP, 'Line',{'Pattern':pstyle})
                pointlist = points.strip().rstrip('/')
                out.text = pointlist
                elem = pointlist.split('/')
                for i in elem:
                    if len(i) <=5:
                        SIDLabel.add(i)
                        SIDpts.add(i)
            elif proctype == 'STAR':
                STARMAP.append(XML.Comment(f'{procname}'))
                out = XML.SubElement(STARMAP, 'Line',{'Pattern':pstyle})
                pointlist = points.strip().rstrip('/')
                out.text = pointlist
                elem = pointlist.split('/')
                for i in elem:
                    if len(i) <=5:
                        STARLabel.add(i)
                        STARpts.add(i)
            elif proctype == 'APPTR':   
                if printAPPTR:
                    out = XML.SubElement(APPTRMAP, 'Line',{'Pattern':pstyle})
                    pointlist = points.strip().rstrip('/')
                    out.text = pointlist
                    elem = pointlist.split('/')  
                    for i in elem:
                        if len(i) <=5:
                            APPTRLabel.add(i)
                            APPpts.add(i)
            else:
                continue
    for i in STARpts:
        out = XML.SubElement(STARsymbol,'Point')
        out.text = i
    for i in SIDpts:
        out = XML.SubElement(SIDsymbol,'Point')
        out.text = i
    for i in APPpts:
        out = XML.SubElement(APPTRsymbol, 'Point')
        out.text = i
    for i in SIDLabel:
        out = XML.SubElement(SIDLabels, 'Point')
        out.text = i
    for i in STARLabel:
        out = XML.SubElement(STARLabels, 'Point')
        out.text = i
    for i in APPTRLabel:
        out = XML.SubElement(APPLabels, 'Point')
        out.text = i
    #XML end wrapping up and writing
    tree = XML.ElementTree(Maps)
    XML.indent(Maps, space="    ")
    tree.write(f"./output/{ICAO}/{ICAO}_RW{rwy}.xml", encoding="utf-8", xml_declaration=True)

def writerwys(ICAO):
    plookup = lookup(ICAO)
    lat = str(plookup['lat'])
    lon = str(plookup['lon'])
    Center = formatcoord(lat, lon)

    Maps = XML.Element('Maps')
    root = XML.SubElement(Maps,'Map', {
        'Type':'System',
        'Name':f'{ICAO}_RUNWAYS',
        'Priority':'3',
        'Center':Center
    })

    processed = set()   # runways we already handled

    for rwy_data in plookup['rwys']:
        rwy = str(rwy_data[0])
        rrecip = reciprwy(rwy)

        # Skip if already handled this pair
        if rwy in processed or rrecip in processed:
            continue

        # Mark both as handled
        processed.add(rwy)
        processed.add(rrecip)

        latlon1 = formatcoord(rwy_data[1], rwy_data[2])

        # Now find reciprocal position
        latlon2 = None
        for j in plookup['rwys']:
            if j[0] == rrecip:
                latlon2 = formatcoord(j[1], j[2])
                break

        # If reciprocal wasn’t found, skip
        if latlon2 is None:
            continue

        # Write BOTH in a single pass
        XML.SubElement(root, 'Threshold', {
            'Name': f'{ICAO}_{rwy}',
            'Position': latlon1
        })

        XML.SubElement(root, 'Threshold', {
            'Name': f'{ICAO}_{rrecip}',
            'Position': latlon2
        })

    tree = XML.ElementTree(Maps)
    XML.indent(Maps, space="    ")
    tree.write(f"./output/{ICAO}/{ICAO}_RWYS.xml",
               encoding="utf-8", xml_declaration=True)


def style(ptype, sidpat ='Dotted', starpat ='Dashed', transpat = 'Dashed'):
    if ptype == 'SID':
        return sidpat
    elif ptype == 'STAR':
        return starpat
    elif ptype == 'APPTR':
        return transpat
    else:
        return 'Solid'
airport_db = {}
current_icao = None

for line in Airports:
    parts = line.strip().split(',')
    if not parts: continue
    
    if parts[0] == 'A':
        current_icao = parts[1]
        airport_db[current_icao] = {
            'name': parts[2],
            'lat': float(parts[3]),
            'lon': float(parts[4]),
            'rwys': []
        }
    elif line.startswith('R') and current_icao:
        # Add runway data to the CURRENT airport's list
        # Assuming columns: ID, lat, lon, heading
        runway_data = [parts[1], float(parts[8]), float(parts[9]), int(parts[2])]
        airport_db[current_icao]['rwys'].append(runway_data)

def lookup(ICAO):
    return airport_db.get(ICAO)

def main(ICAO,APPTR):
    os.makedirs(f'./output/{ICAO}/', exist_ok=True)
    data = drawall(ICAO)
    writerwys(ICAO)
    airport = lookup(ICAO)
    for i in airport['rwys']:
        writexml(ICAO,data,f'{i[0]}',APPTR)

import fnmatch

def loop(user_input,APPTR):
    # Split comma-separated inputs and strip whitespace
    patterns = [p.strip() for p in user_input.split(',') if p.strip()]

    # Load all ICAO codes
    procs = []
    icaos = []

    f = os.listdir('./Navdata/Proc')
    for line in f:
        procs.append(line.rstrip('.txt'))

    for line in Airports:
        if line.startswith('A'):
            parts = line.split(',')
            if len(parts) >= 2:
                icaos.append(parts[1].strip())

    valid = set(procs) & set(icaos)

    # Gather matches for all patterns
    matches = set()
    for pat in patterns:
        for icao in valid:
            if fnmatch.fnmatch(icao, pat):
                matches.add(icao)

    # Execute main() for each match
    for icao in sorted(matches):
        print(f"Running main({icao})...")
        main(icao,APPTR)

loop('WI*,WA*',False)
end = time.perf_counter()

print("Execution time:", (end - start)*1000, "miliseconds")