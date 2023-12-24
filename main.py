#!/bin/env python3

from tkinter.filedialog import askopenfilename, askdirectory
from PIL import Image
import tkinter as tk
import plistlib
import colorama
import fnmatch
import pprint
import shutil
import copy
import sys
import os

def log(string, *formatting, end="\n"):
    print("[+] " + string % formatting, end=end)

def error(string, *formatting):
    print("\x1b[48;5;9m\x1b[38;5;15m[!] " + string % formatting + "\x1b[0m")
    sys.exit(1)

def fmtperc(perc):
    perc = round(perc, 2)
    perc = f"{perc:0<5}"
    return perc

def parse_dicts(dicts):
    dicts = copy.copy(dicts)
    
    res = []

    if dicts[0] != "{":
        error("mangled plist file (doesn't start with '{')")

    dicts = dicts[1:]

    if dicts[0] == "{":
        res.append(parse_dicts(dicts)[0])
        dicts = dicts[dicts.find("}") + 2:]
        res.append(parse_dicts(dicts)[0])
        dicts = dicts[dicts.find("}") + 2:]

    else:
        colon = dicts.find(",")
        if colon == -1: error("mangled plist file (cant find colon)")
        num0 = int(dicts[:colon])
        dicts = dicts[colon + 1:]
        curlyend = dicts.find("}")
        if curlyend == -1: error("mangled plist file (cant find end curly)")
        num1 = int(dicts[:curlyend])
        dicts = dicts[curlyend + 1:]
        res.append([num0, num1])

    return res


def progressbar(cur, pmax, length=30):
    cur = cur / pmax
    return ("|" + "=" * int(cur * length) + (">" if cur != 1.0 else "") + ":" * int(length - 1 - int(cur * length))) + "| " + fmtperc(cur * 100) + "%"

def split(file_name):
    if not os.path.isfile(file_name):
        error("plist %s does not exist", file_name)

    plist_file = plistlib.load(open(file_name, "rb"), fmt=plistlib.FMT_XML)
    folder_name = file_name + "_split"

    if os.path.isdir(folder_name):
        log("found folder named \"%s\", deleting", os.path.basename(folder_name))
        shutil.rmtree(folder_name)

    elif os.path.isfile(folder_name):
        log("found file named \"%s\", deleting", os.path.basename(folder_name))
        os.remove(folder_name)

    log("creating folder \"%s\"", os.path.basename(folder_name))
    os.mkdir(folder_name)

    log("ripping metadata")
    metadata = plist_file["metadata"]
    metadata.pop("size")
    metadata.pop("smartupdate")
    metadata.pop("pixelFormat")
    open(os.path.join(folder_name, "textureMeta.plist"), "wb") \
            .write(plistlib.dumps(metadata, fmt=plistlib.FMT_XML))

    log("ripping textures")
    #                                          v    rob... why   v
    image = Image.open(plist_file["metadata"]["realTextureFileName"])
    for k, i in enumerate(plist_file["frames"].items()):
        log("done: %s", progressbar(k, len(plist_file["frames"]) - 1), end="\r")
        parsed = parse_dicts(i[1]["textureRect"])

        left, top = parsed[0][0], parsed[0][1]
        if i[1]["textureRotated"]:
            right, bottom = parsed[1][1] + parsed[0][0], parsed[1][0] + parsed[0][1]
        else:
            right, bottom = parsed[1][0] + parsed[0][0], parsed[1][1] + parsed[0][1]

        cropped = image.crop((left, top, right, bottom))

        if i[1]["textureRotated"]:
            cropped = cropped.rotate(90, expand=True)

        cropped.save(os.path.join(folder_name, i[0]))
        i[1].pop("textureRect")
        i[1].pop("textureRotated")
        i[1].pop("spriteSize")
        open(os.path.join(folder_name, i[0] + ".plist"), "wb").write(plistlib.dumps(i[1], fmt=plistlib.FMT_XML))

    print(" " * os.get_terminal_size()[0], end="\r")

def merge(folder_name, fw=4096, update_callback=lambda x, m: None):
    if not os.path.isdir(folder_name):
        error("folder \"%s\" does not exists or is a file", folder_name)

    file_list = os.listdir(folder_name)

    log("loading all images")

    images = []

    for i in fnmatch.filter(file_list, "*.plist"):
        if i == "textureMeta.plist": continue
        image_meta = plistlib.load(open(os.path.join(folder_name, i), "rb"), fmt=plistlib.FMT_XML)
        image = Image.open(os.path.join(folder_name, i)[:-6])

        images.append((image, image_meta, i))

    metadata = plistlib.load(open(os.path.join(folder_name, "textureMeta.plist"), "rb"), fmt=plistlib.FMT_XML)

    texture_meta = {"frames": {}, "metadata": metadata}
    
    texture_width = max(fw, max(map(lambda x: x[0].width, images)))

    images_line = []

    image_stroke = []
    stroke_length = 0
    cur_height = 0
    for k, i in enumerate(images):
        if i[0].width + stroke_length > texture_width:
            images_line.append((cur_height, image_stroke))
            stroke_length = 0
            cur_height += max(map(lambda x: x[1][0].height, image_stroke))
            image_stroke = []
        image_stroke.append((k, i))
        stroke_length += i[0].width

    images_line.append((cur_height, image_stroke))
    cur_height += max(map(lambda x: x[1][0].height, image_stroke))
    
    texture_height = cur_height

    texture = Image.new("RGBA", (texture_width, texture_height))
    
    for h, i in images_line:
        cw = 0
        for j in i:
            k, j = j
            update_callback(k, len(images) - 1)
            print(" " * os.get_terminal_size()[0], end="\r")
            log("done: %s", progressbar(k, len(images) - 1), end="\r")
            image = j[0]
            image_meta = j[1]

            image_meta["spriteSize"] = "{%d,%d}" % image.size
            image_meta["textureRect"] = "{{%i,%i},%s}" % (cw, h, image_meta["spriteSize"])
            texture.paste(image, (cw, h))
            
            image_meta["textureRotated"] = False
            #if image.height > image.width:
            #    image_meta["textureRotated"] = True
            #    image = image.rotate(270, expand=True)

            texture_meta["frames"][j[2][:-6]] = image_meta
                
            cw += image.width
    
    texture_meta["metadata"]["size"] = "{%i,%i}" % texture.size
    texture_meta["metadata"]["smartupdate"] = "$none"
    texture_meta["metadata"]["pixelFormat"] = "RGBA8888"

    print(" " * os.get_terminal_size()[0], end="\r")

    log("saving texture & meta")

    texture.save(texture_meta["metadata"]["realTextureFileName"], "png")
    open(texture_meta["metadata"]["realTextureFileName"].rsplit(".", 1)[0] + ".plist", "wb").write(plistlib.dumps(texture_meta, fmt=plistlib.FMT_XML))

def get_file():
    tk.Tk().withdraw()
    return askopenfilename()

def get_folder():
    tk.Tk().withdraw()
    return askdirectory()

def interactive_mode():
    log("select mode:")
    log("- [s]plit")
    log("- [m]erge")
    
    mode = input("[?] selected option (s,m): ")
        
    while mode not in ("s", "m"):
        mode = input("[?] s,m:  ")
    
    if mode == "s":
        log("select .plist file")
        split(get_file())
    if mode == "m":
        log("select folder")
        merge(get_folder())
    
    log("\x1b[48;5;10m\x1b[38;5;0mdone\x1b[0m")

    sys.exit(0)

if __name__ == "__main__":
    colorama.init()
    log("GD Texture Splitter made by aciddev")
    argv = copy.copy(sys.argv)
    program_name = argv.pop(0)
    if len(argv) == 0:
        interactive_mode()
    
    mode = argv.pop(0)

    if mode not in ("-s", "-c"):
        error("unknown mode; available: -s (split), -c (combine)")

    if mode == "-s":
        split(argv.pop(0))
    elif mode == "-c":
        merge(argv.pop(0))
    
    log("\x1b[48;5;10m\x1b[38;5;0mdone\x1b[0m")

