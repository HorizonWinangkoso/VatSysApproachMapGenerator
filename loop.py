import os
import xml.etree.ElementTree as ET
import argparse
from xml.dom import minidom
import re
import math
from fnmatch import fnmatch

parser = argparse.ArgumentParser()
parser.add_argument('--icao', type=str, required=True, help='Exact ICAO or wildcard pattern')
parser.add_argument('--suicide', type=str)
parser.add_argument('--colourful', action='store_true')
args = parser.parse_args()

pattern = args.icao.upper()
suicide = args.suicide
colourful = args.colourful

dir_path = "Output"
os.makedirs(dir_path, exist_ok=True)

with open('Navdata/Airports.txt', 'r') as f:
    lines = f.readlines()

# Expand wildcard ICAO list
icao_list = []
for line in lines:
    parts = line.split(',')
    if parts[0] == 'A':
        code = parts[1].upper()
        if fnmatch(code, pattern):
            icao_list.append(code)

if not icao_list:
    print(f"No ICAO codes found matching: {pattern}")
    exit(1)


def format_position(lat, lon):
    lat_sign = '+' if lat >= 0 else '-'
    lon_sign = '+' if lon >= 0 else '-'
    lat = abs(lat)
    lon = abs(lon)
    lat_str = f"{lat_sign}{lat:02.4f}".zfill(8)
    lon_str = f"{lon_sign}{lon:03.4f}".zfill(9)
    return f"{lat_str}{lon_str}"


def generate_arc(lat_center, lon_center, start_radial, end_radial, radius, step_degrees=10):
    lat_center = math.radians(lat_center)
    lon_center = math.radians(lon_center)
    start_radial = math.radians(start_radial)
    end_radial = math.radians(end_radial)
    radius = radius / 3440.07

    diff_clockwise = (end_radial - start_radial) % (2 * math.pi)
    diff_counterclockwise = (start_radial - end_radial) % (2 * math.pi)

    if diff_clockwise <= diff_counterclockwise:
        step = math.radians(abs(step_degrees))
        for_brng_end = start_radial + diff_clockwise
    else:
        step = math.radians(-abs(step_degrees))
        for_brng_end = start_radial - diff_counterclockwise

    coords = []
    brng = start_radial

    while (step > 0 and brng <= for_brng_end) or (step < 0 and brng >= for_brng_end):
        lat = math.asin(math.sin(lat_center) * math.cos(radius) +
                        math.cos(lat_center) * math.sin(radius) * math.cos(brng))
        lon = lon_center + math.atan2(math.sin(brng) * math.sin(radius) * math.cos(lat_center),
                                      math.cos(radius) - math.sin(lat_center) * math.sin(lat))
        coords.append(format_position(math.degrees(lat), math.degrees(lon)))
        brng += step

    return coords


def opposite_runway_number(rwy):
    base = rwy.rstrip('LRC')
    base = int(base)
    opp = base + 18 if base <= 18 else base - 18

    if 'L' in rwy:
        suf = 'R'
    elif 'R' in rwy:
        suf = 'L'
    else:
        suf = ''

    return f"{opp:02d}{suf}"


def get_opposite_heading(hdg):
    hdg = int(hdg)
    return hdg + 180 if hdg < 180 else hdg - 180


def remove_runway_map(current_icao):
    icao_out_dir = os.path.join(dir_path, current_icao)
    file_path = os.path.join(icao_out_dir, f"{current_icao}_RW{opposite_runway_number(suicide)}_RECIP.xml")
    if os.path.exists(file_path):
        os.remove(file_path)


# ------------------------------------------------------------
# MAIN LOOP OVER MULTIPLE ICAOS
# ------------------------------------------------------------
for current_icao in icao_list:
    print(f"\n=== Processing {current_icao} ===")

    # Create folder per ICAO
    icao_out_dir = os.path.join(dir_path, current_icao)
    os.makedirs(icao_out_dir, exist_ok=True)

    # Find airport row first
    for i, line in enumerate(lines):
        parts = line.split(',')
        if parts[0] == 'A' and parts[1] == current_icao:

            lat, lon = map(float, parts[3:5])
            airport_coords = format_position(lat, lon)

            runway_lines = []
            unique_runway_numbers = set()

            for j in range(i + 1, len(lines)):
                if lines[j].startswith('R,'):
                    r_parts = lines[j].split(',')
                    runway_lines.append(lines[j])
                    runway_number = r_parts[1].rstrip('LRC')
                    unique_runway_numbers.add(runway_number)
                else:
                    break

            # PROCESS EACH RUNWAY
            for runway_number in unique_runway_numbers:

                # Cleanup existing file(s)
                if suicide is not None:
                    outfile = os.path.join(icao_out_dir, f"{current_icao}_RW{runway_number}_RECIP.xml")
                else:
                    outfile = os.path.join(icao_out_dir, f"{current_icao}_RW{runway_number}.xml")

                if os.path.exists(outfile):
                    os.remove(outfile)

                root = ET.Element("Maps")

                # Each runway gets its own map object
                map_elem = ET.SubElement(root, "Map")
                map_elem.set("Type", "System")
                map_elem.set("Name", f"{current_icao}_RW{runway_number}" if suicide is None else f"{current_icao}_RW{runway_number}_RECIP")
                map_elem.set("Priority", "3")
                map_elem.set("Center", airport_coords)

                # Add runway and thresholds
                for r_line in runway_lines:
                    r_parts = r_line.split(',')
                    r_number = r_parts[1]
                    r_lat, r_lon = map(float, r_parts[8:10])
                    r_coords = format_position(r_lat, r_lon)
                    r_heading = r_parts[2]

                    runway_elem = ET.SubElement(map_elem, "Runway")
                    runway_elem.set("Name", r_number)

                    thr1 = ET.SubElement(runway_elem, "Threshold")
                    thr1.set("Name", r_number)
                    thr1.set("Position", r_coords)
                    thr1.set("ExtendedCentrelineTrack", str(get_opposite_heading(r_heading)))
                    thr1.set("ExtendedCentrelineLength", "12")
                    thr1.set("ExtendedCentrelineWidth", "1")
                    thr1.set("ExtendedCentrelineTickInterval", "1")

                    opposite_num = opposite_runway_number(r_number)
                    opposite_coords = ''

                    for opp_line in runway_lines:
                        opp_parts = opp_line.split(',')
                        if opp_parts[1] == opposite_num:
                            olat, olon = map(float, opp_parts[8:10])
                            opposite_coords = format_position(olat, olon)
                            break

                    thr2 = ET.SubElement(runway_elem, "Threshold")
                    thr2.set("Name", opposite_num)
                    thr2.set("Position", opposite_coords)

                # WAYPOINT COLLECTION
                all_waypoints = set()

                # ---------------------------------------------------
                # SIDs
                # ---------------------------------------------------
                try:
                    with open(f"Navdata/Proc/{current_icao}.txt", 'r') as f:
                        sid_lines = f.readlines()
                except FileNotFoundError:
                    sid_lines = []

                if sid_lines:
                    for sid_line in sid_lines:
                        sid_parts = sid_line.split(',')
                        if sid_parts[0] == "SID" and (sid_parts[2] == runway_number):
                            sid_name = sid_parts[1]
                            map_elem.append(ET.Comment(f"SID: {sid_name}, Runway: {runway_number}"))

                            sid_line_elem = ET.SubElement(map_elem, "Line")
                            sid_line_elem.set("Pattern", "Dotted")
                            if colourful:
                                sid_line_elem.set("CustomColourName", "NoiseTurquoise")

                            sid_line_elem.text = opposite_coords + "/"

                            index = sid_lines.index(sid_line)
                            for waypoint in sid_lines[index + 1:]:
                                if waypoint.startswith("SID") or waypoint.strip() == "":
                                    break
                                if waypoint.startswith(("AF")):
                                    wp = waypoint.split(',')
                                    arc = generate_arc(lat, lon, float(wp[8]), float(wp[6]), float(wp[7]))
                                    for c in arc:
                                        sid_line_elem.text += c + "/"
                                elif waypoint.startswith(("VA", "DF", "TF", "CF")):
                                    wp = waypoint.split(',')
                                    name = wp[1]
                                    if name != "0":
                                        sid_line_elem.text += name + "/"
                                        all_waypoints.add(name)

                            if sid_line_elem.text.endswith("/"):
                                sid_line_elem.text = sid_line_elem.text[:-1]

                # ---------------------------------------------------
                # STAR
                # ---------------------------------------------------
                try:
                    with open(f"Navdata/Proc/{current_icao}.txt", 'r') as f:
                        star_lines = f.readlines()
                except FileNotFoundError:
                    star_lines = []

                if star_lines:
                    for star_line in star_lines:
                        sp = star_line.split(',')
                        if sp[0] == "STAR" and (sp[2] == runway_number or sp[2] == "ALL"):
                            star_name = sp[1]
                            map_elem.append(ET.Comment(f"STAR: {star_name}, Runway: {runway_number}"))

                            star_line_elem = ET.SubElement(map_elem, "Line")
                            star_line_elem.set("Pattern", "Dashed")

                            if colourful:
                                star_line_elem.set("CustomColourName", "MellowYellow")

                            star_line_elem.text = ""
                            used = set()

                            index = star_lines.index(star_line)
                            for waypoint in star_lines[index + 1:]:

                                wp = waypoint.split(',')
                                if len(wp) < 2:
                                    continue

                                token = wp[0].strip().upper()

                                if token in ("STAR", "END", "APPTR", "FINAL"):
                                    break

                                if waypoint.startswith("AF"):
                                    arc = generate_arc(lat, lon, float(wp[8]), float(wp[6]), float(wp[7]))
                                    for c in arc:
                                        star_line_elem.text += c + "/"
                                else:
                                    name = wp[1]
                                    if name != "0" and name not in used:
                                        star_line_elem.text += name + "/"
                                        used.add(name)
                                        all_waypoints.add(name)

                            if star_line_elem.text.endswith("/"):
                                star_line_elem.text = star_line_elem.text[:-1]

                # ---------------------------------------------------
                # SYMBOLS
                # ---------------------------------------------------
                if all_waypoints:
                    symbol = ET.SubElement(map_elem, "Symbol")
                    symbol.set("Type", "SolidTriangle")
                    if colourful:
                        symbol.set("CustomColourName", "LoonyMaroons")

                    for wp in all_waypoints:
                        ET.SubElement(symbol, "Point").text = wp

                    lbl = ET.SubElement(root, "Map")
                    lbl.set("Type", "System")
                    lbl.set("Priority", "3")
                    lbl.set("Center", airport_coords)

                    if suicide:
                        lbl.set("Name", f"{current_icao}_RW{runway_number}_RECIP_NAMES")
                    else:
                        lbl.set("Name", f"{current_icao}_RW{runway_number}_NAMES")

                    if colourful:
                        lbl.set("CustomColourName", "LoonyMaroons")

                    label_elem = ET.SubElement(lbl, "Label")
                    for wp in all_waypoints:
                        point = ET.SubElement(label_elem, "Point")
                        point.text = wp

                # ---------------------------------------------------
                # WRITE XML
                # ---------------------------------------------------
                ET.indent(root, space="    ")

                with open(outfile, "wb") as f:
                    f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
                    ET.ElementTree(root).write(f, encoding="utf-8")

                if suicide:
                    remove_runway_map(current_icao)

            break  # stop once airport is processed
