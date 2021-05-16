import argparse
import subprocess
import os
import numpy as np
from geopy.distance import distance

from xml.dom import minidom
import xml.etree.ElementTree as ET

import matplotlib
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


import folium
from folium.features import DivIcon
from datetime import datetime, timedelta


class TrackData:
    def __init__(self):
        self.segments = []


class SegmentData:
    def __init__(self):
        self.datapoints = []


def _get_waypoint_data(waypoint):
    lap_string = waypoint.getElementsByTagName('name')[0].firstChild.data  # only one result
    lapnumber = lap_string.replace('LAP', '')
    lat = waypoint.getAttribute('lat')
    lon = waypoint.getAttribute('lon')
    data = {'LAP': lapnumber,
            'lat': lat,
            'lon': lon}
    return data


def get_waypoints_from_gpx(gpxfile):
    waypointdata = []
    for waypoint in minidom.parse(gpxfile).getElementsByTagName("wpt"):
        waypointdata.append(_get_waypoint_data(waypoint))
    return waypointdata


def _merge(file1, file2, outfile):
    "merges two gpx files, generated by different babel flags, into one"
    gpx1 = minidom.parse(file1)
    gpx2 = minidom.parse(file2)
    root = ET.Element("gpx", {'creator': "me", 'prog_used': "gpsbabel"})
    for waypoint in gpx1.getElementsByTagName('wpt'):
        _ = ET.SubElement(root, 'wpt', _get_waypoint_data(waypoint))

    outstr = ET.tostring(root)
    prettyxml = minidom.parseString(outstr)
    with open(outfile, "w") as f:
        f.write(prettyxml.toprettyxml(indent='\t', newl='\n'))


def convert_fit_to_gpx(fitfile):
    speedfile = '/tmp/speed.gpx'
    hrfile = '/tmp/hr.gpx'
    subprocess.call(["gpsbabel", "-t", "-i", "garmin_fit", "-x", "track,speed", "-f", fitfile,
                     "-o", "gpx", "-F", speedfile])
    subprocess.call(["gpsbabel", "-t", "-i", "garmin_fit", "-f", fitfile,
                     "-o", "gpx,garminextensions", "-F", hrfile])
    _merge(speedfile, hrfile, fitfile.replace('.fit', '.gpx'))


def process_gpx_file(filename):
    gpx = minidom.parse(filename)
    tracks = []
    for track in gpx.getElementsByTagName('trk'):
        tdata = TrackData()
        for tracksegment in track.getElementsByTagName('trkseg'):
            seg = SegmentData()
            for trackpoint in tracksegment.getElementsByTagName('trkpt'):
                seg.datapoints.append(get_data_from_point(trackpoint))
            tdata.segments.append(seg)
        tracks.append(tdata)
    return tracks


def get_data_from_point(trackpoint):
    lat = trackpoint.getAttribute('lat')
    lon = trackpoint.getAttribute('lon')
    ele = trackpoint.getElementsByTagName('ele')[0].firstChild.data
    time = trackpoint.getElementsByTagName('time')[0].firstChild.data
    speed = trackpoint.getElementsByTagName('speed')[0].firstChild.data
    atemp = trackpoint.getElementsByTagName('gpxtpx:atemp')[0].firstChild.data
    hr = trackpoint.getElementsByTagName('gpxtpx:hr')[0].firstChild.data
    cad = trackpoint.getElementsByTagName('gpxtpx:cad')[0].firstChild.data

    data = {
        'lat': float(lat),
        'lon': float(lon),
        'ele': float(ele),
        'atemp': float(atemp),
        'time': time,
        'hr': float(hr),
        'cad': float(cad),
        'speed': float(speed)
    }
    return data


def get_dist_gps(dp1, dp2):
    lat1 = dp1['lat']
    lon1 = dp1['lon']
    lat2 = dp2['lat']
    lon2 = dp2['lon']
    return distance((lat1, lon1), (lat2, lon2)).km


def _get_dist(dist_inc):
    dist = [0]
    for inc in dist_inc[1:]:
        dist.append(dist[-1] + inc)
    return dist


def gps_dist(flat):
    dist_inc = [0]
    for index, dp in enumerate(flat[1:]):
        dist_inc.append(get_dist_gps(flat[index], dp))
    return _get_dist(dist_inc)


def speed_dist(duration, speeds):
    dist_inc = [0]
    for i in range(len(duration) - 1):
        dt = duration[i+1] - duration[i]
        d = 1/2*(speeds[i] + speeds[i+1])*dt
        dist_inc.append(d)
    dist_meter = _get_dist(dist_inc)
    dist_km = [1/1000*d for d in dist_meter]
    return dist_km


def main():
    # fitfile = './B5CE0704.fit'
    # convert_fit_to_gpx(fitfile)

    gpxfile = './qmapshack_export.gpx'
    tracks = process_gpx_file(gpxfile)
    waypointdata = get_waypoints_from_gpx(gpxfile)

    flat = []
    num_tracks = int(len(tracks))
    print(f"have {num_tracks} tracks")
    for track in tracks:
        num_seg = int(len(track.segments))
        print(f"Track has {num_seg} segments")
        for seg in track.segments:
            flat = flat + seg.datapoints


    p1 = tracks[0].segments[0].datapoints[-1]
    p2 = tracks[0].segments[1].datapoints[0]


    datetimes = [datetime.strptime(dp['time'], '%Y-%m-%dT%H:%M:%S.000Z') for dp in flat]
    total_time = (datetimes[-1] - datetimes[0]).total_seconds()/(60*60)  # in h
    duration_sec = [ (d - datetimes[0]).total_seconds() for d in datetimes]
    duration_plot = [mdates.date2num(d) - mdates.date2num(datetimes[0]) for d in datetimes]
    speeds_mps = [dp['speed'] for dp in flat]
    speeds_kmh = [3.6*s for s in speeds_mps]  # m/s, need km/h
    paces = [(16+2/3)/dp['speed'] for dp in flat]
    elevation = [dp['ele'] for dp in flat]

    dist_gps = gps_dist(flat)
    dist_speed = speed_dist(duration_sec, speeds_mps)
    dist = [1/2*(d1 + d2) for d1, d2 in zip(dist_gps, dist_speed)]



    average_pace = 60/(dist[-1]/total_time)
    print(f"Length: {dist[-1]:.2f}")
    d, r = divmod(total_time, 1)
    r1, r2 = divmod(60*r, 1)
    print(f"Time: {int(d)}:{int(r1)}:{r2*60:.0f}")
    d, r = divmod(average_pace, 1)
    print(f"Average pace {int(d)}:{r*60:.0f}")
    offset = get_dist_gps(p1, p2)
    print(f"Offset due to multiple segments {offset}km")
    average_pace_list = [average_pace for dp in flat]


    hr = [dp['hr'] for dp in flat]
    fig, ax = plt.subplots()
    # ax.set_ylim([100, 190])

    # ax.xaxis.set_major_formatter(mdates.DateFormatter('%H-%M'))
    # ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=2))
    # ax.xaxis.set_minor_locator(mdates.SecondLocator(interval=30))
    # ax.plot(duration_plot, hr)
    # ax.plot(duration_plot, speeds_kmh)
    # ax.plot(duration_plot, elevation)
    # fig.autofmt_xdate()

    ax.plot(dist, average_pace_list, ls='--')
    ax.plot(dist, paces)

    # ax.format_xdata = mdates.DateFormatter('%M-%S')
    plt.show()


if __name__ == "__main__":
    main()
