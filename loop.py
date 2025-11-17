import os
import xml.etree.ElementTree as ET
import math
from xml.dom import minidom
from concurrent.futures import ThreadPoolExecutor
import fnmatch

# --- config ---
BASE_OUTPUT_DIR = "Output"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

with open('Navdata/Airports.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()


# --- helpers (unchanged behavior) ---
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
    # radius in nautical miles -> angular distance
    radius = radius / 3440.07

    diff_clockwise = (end_radial - start_radial) % (2 * math.pi)
    diff_counter_clockwise = (start_radial - end_radial) % (2 * math.pi)

    if diff_clockwise <= diff_counter_clockwise:
        step_degrees = abs(step_degrees)
        end_bearing = start_radial + diff_clockwise
    else:
        step_degrees = -abs(step_degrees)
        end_bearing = start_radial - diff_counter_clockwise

    coordinates = []
    brng = start_radial
    step_rad = math.radians(step_degrees)
    while (step_degrees > 0 and brng <= end_bearing) or (step_degrees < 0 and brng >= end_bearing):
        lat = math.asin(math.sin(lat_center) * math.cos(radius) +
                        math.cos(lat_center) * math.sin(radius) * math.cos(brng))
        lon = lon_center + math.atan2(math.sin(brng) * math.sin(radius) * math.cos(lat_center),
                                      math.cos(radius) - math.sin(lat_center) * math.sin(lat))
        coordinates.append(format_position(math.degrees(lat), math.degrees(lon)))
        brng += step_rad
    return coordinates


def opposite_runway_number(runway_number):
    runway_number_base = runway_number.rstrip('LRC')
    runway_number_base = int(runway_number_base)

    if runway_number_base <= 18:
        opposite_runway_number_base = runway_number_base + 18
    else:
        opposite_runway_number_base = runway_number_base - 18

    if 'L' in runway_number:
        opposite_runway_number_suffix = 'R'
    elif 'R' in runway_number:
        opposite_runway_number_suffix = 'L'
    else:
        opposite_runway_number_suffix = ''

    return f"{opposite_runway_number_base:02d}{opposite_runway_number_suffix}"


def get_opposite_heading(heading):
    heading = int(float(heading))
    if heading < 180:
        return heading + 180
    else:
        return heading - 180


def prettify_etree_bytes(element):
    """Return pretty-printed bytes with XML declaration."""
    rough = ET.tostring(element, encoding='utf-8')
    parsed = minidom.parseString(rough)
    pretty_str = parsed.toprettyxml(indent="    ")
    # remove blank lines
    lines_pk = [ln for ln in pretty_str.splitlines() if ln.strip()]
    joined = "\n".join(lines_pk)
    return ('<?xml version="1.0" encoding="utf-8"?>\n' + joined).encode('utf-8')


# --- thread-safe main ---
def main(icao_code: str, bundir: str = None, colourful: bool = False,
         base_output_dir: str = BASE_OUTPUT_DIR, all_lines: list = None):
    """
    Thread-safe refactor of your original main().
    - icao_code: airport code to process (string)
    - bundir: original 'suicide' param (string or None)
    - colourful: original 'colourful' boolean flag
    - base_output_dir: root output directory
    - all_lines: list of lines from Navdata/Airports.txt
    """
    if all_lines is None:
        raise ValueError("all_lines must be provided")

    icao = icao_code.strip().upper()
    suicide = bundir  # preserve original name usage
    os.makedirs(base_output_dir, exist_ok=True)

    # ICAO-local output dir (isolates files per thread)
    icao_out_dir = os.path.join(base_output_dir, icao)
    os.makedirs(icao_out_dir, exist_ok=True)

    def remove_runway_map_local(icao_local, suicide_local):
        """Remove the reciprocal map file derived from suicide_local if it exists
           in both base_output_dir and the ICAO-specific dir (mimic original behaviour)."""
        if suicide_local is None:
            return
        try:
            opp = opposite_runway_number(suicide_local)
        except Exception:
            return
        # root-level file (original code used dir_path root sometimes)
        root_path = os.path.join(base_output_dir, f"{icao_local}_RW{opp}_RECIP.xml")
        if os.path.exists(root_path):
            try:
                os.remove(root_path)
            except OSError:
                pass
        # ICAO subdir file
        sub_path = os.path.join(icao_out_dir, f"{icao_local}_RW{opp}_RECIP.xml")
        if os.path.exists(sub_path):
            try:
                os.remove(sub_path)
            except OSError:
                pass

    # iterate through airports to find the matching A, line
    active = False
    airport_coords = None

    for i, raw_line in enumerate(all_lines):
        line = raw_line.rstrip("\n")
        parts = line.split(',')
        if not parts:
            continue

        if parts[0] == 'A' and len(parts) > 1 and parts[1].strip().upper() == icao:
            # found the airport block
            active = True
            try:
                lat, lon = map(float, parts[3:5])
                airport_coords = format_position(lat, lon)
            except Exception:
                airport_coords = ''
            # collect runway lines directly after this
            runway_lines = []
            unique_runway_numbers = set()
            for j in range(i + 1, len(all_lines)):
                if all_lines[j].startswith('R,'):
                    runway_lines.append(all_lines[j].strip())
                    runway_number = all_lines[j].split(',')[1].rstrip('LRC')
                    unique_runway_numbers.add(runway_number)
                else:
                    break

            # process each unique runway number
            for runway_number in unique_runway_numbers:
                # determine intended output filename root (root-level and per-icao)
                # The original code sometimes created files at base dir and also in per-icao dir.
                # We'll write only into the per-icao folder, but still remove any root-level file when requested.
                out_filename_base = f"{icao}_RW{runway_number}"
                if suicide is not None:
                    out_filename_base_rec = f"{icao}_RW{runway_number}_RECIP"
                else:
                    out_filename_base_rec = out_filename_base

                # remove any existing same-named files (per-icao)
                file_path = os.path.join(icao_out_dir, out_filename_base_rec + ".xml")
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

                # Build XML root for this runway (per run through runway_lines we will write to per-icao files)
                root = ET.Element("Maps")
                map_elem = ET.SubElement(root, "Map")
                map_elem.set("Type", "System")
                map_elem.set("Name", f"{icao}_RW{runway_number}")
                map_elem.set("Priority", "3")
                if airport_coords:
                    map_elem.set("Center", airport_coords)

                # iterate the actual runway lines to create runway entries
                for r_line in runway_lines:
        r_parts = r_line.split(',')
        if len(r_parts) < 10:
            continue

        r_number = r_parts[1]

        # Create a NEW root for this runway ONLY
        root = ET.Element("Maps")

        map_elem = ET.SubElement(root, "Map")
        map_elem.set("Type", "System")
        map_elem.set("Name", f"{icao}_RW{r_number}" + ("_RECIP" if suicide is not None else ""))
        map_elem.set("Priority", "3")

        if airport_coords:
            map_elem.set("Center", airport_coords)

        # --- runway thresholds
        runway_elem = ET.SubElement(map_elem, "Runway")
        runway_elem.set("Name", r_number)

        thr1 = ET.SubElement(runway_elem, "Threshold")
        thr1.set("Name", r_number)
        thr1.set("Position", r_coords)
        thr1.set("ExtendedCentrelineTrack", str(get_opposite_heading(r_heading)))
        thr1.set("ExtendedCentrelineLength", "12")
        thr1.set("ExtendedCentrelineWidth", "1")
        thr1.set("ExtendedCentrelineTickInterval", "1")

        thr2 = ET.SubElement(runway_elem, "Threshold")
        thr2.set("Name", opposite_runway_number(r_number))
        thr2.set("Position", opposite_r_coords)

        # --- SID/STAR generation, waypoints, symbols...
        waypoints = process_procs(map_elem, center_for_sid, match_runway_for_sid)

        if waypoints:
            sym = ET.SubElement(map_elem, "Symbol")
            sym.set("Type", "SolidTriangle")
            if colourful:
                sym.set("CustomColourName", "LoonyMaroons")

            for wp in waypoints:
                p = ET.SubElement(sym, "Point")
                p.text = wp

        # Write ONLY THIS runway as its own file
        filename = os.path.join(icao_dir, f"{icao}_RW{r_number}" + ("_RECIP.xml" if suicide else ".xml"))
        atomic_write(filename, prettify_etree_bytes(root))

        # suicide cleanup if needed
        if suicide is not None:
            remove_recip_map(icao, suicide)

                # End for r_line in runway_lines

                # After processing r_lines, write the outer "root" file once (original code wrote a root file too)
                try:
                    root_bytes = prettify_etree_bytes(root)
                    root_file_path = os.path.join(icao_out_dir, f"{out_filename_base}.xml")
                    with open(root_file_path, 'wb') as rf:
                        rf.write(root_bytes)
                except Exception:
                    try:
                        ET.indent(root, space="    ")
                    except Exception:
                        pass
                    root_file_path = os.path.join(icao_out_dir, f"{out_filename_base}.xml")
                    with open(root_file_path, 'wb') as rf:
                        rf.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
                        ET.ElementTree(root).write(rf, encoding='utf-8')

            # finished processing this ICAO block; break out (original code processed only first match)
            break

    # done main()


# --- gen() that runs multiple matches in parallel ---
def gen(pattern: str, bundir: str = None, colourful: bool = False, max_workers: int = 8):
    """
    Find codes in the global 'lines' list that match the pattern,
    and call main(code, bundir, colourful, BASE_OUTPUT_DIR, lines) in a thread pool.
    """
    pattern = pattern.upper()
    matches = []
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("A,"):
            parts = line.split(",")
            if len(parts) >= 2:
                code = parts[1].upper().strip()
                if fnmatch.fnmatch(code, pattern):
                    matches.append(code)

    if not matches:
        print("No matches for pattern:", pattern)
        return

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = []
        for code in matches:
            futures.append(pool.submit(main, code, bundir, colourful, BASE_OUTPUT_DIR, lines))

        # optional: wait for completion and raise if error
        for f in futures:
            try:
                f.result()
            except Exception as e:
                print("Error processing:", e)

gen('WI*', bundir=None, colourful=False, max_workers=6)
# Example usage:
# gen('WI*', bundir=None, colourful=False, max_workers=6)
# or single-threaded:
# main('WIAA', bundir=None, colourful=True, base_output_dir='Output', all_lines=lines)
