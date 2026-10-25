// The game versions Savage Wind knows, by the build id of their main module (its first 8 bytes as hex, as
// tools/sw_probe.py prints it). The configuration screen sets up the supported ones; a known one that isn't supported
// yet is refused with its own message. tools/game_sites.py VERSIONS is the same list for the code generator
// (tools/test_game_sites.py checks they match); docs/SAVAGE-WIND.md, "Versiones del juego", has the steps for a
// new version. X(version, build id, supported, RomFS files, title id, generic)
// RomFS files: how many its RomFS has with the update applied over the base game (0: not counted). Before copying, the
// setup checks that the chosen RomFS says this version in System/Version.txt and has at least 95% of these files: the
// cartridge's RomFS without the update says its own version, the update's RomFS alone has far fewer files
// (runtime/ui/launcher.mm, check_romfs).
// title id: the program id in exefs/main.npdm (16 lowercase hex digits). A version with an empty build id is told by it
// alone: any main module of that title (tools/game_sites.py VERSIONS has the same). Others: "".
// generic: 1 = not Breath of the Wild. Its RomFS has no System/Version.txt to check (only that it isn't empty, and the
// file count when one is given) and the game code has no BOTW sites (runtime/gamelib.c).
#pragma once

#define GAME_VERSIONS(X)                           \
    X("1.8.2", "de0b6ac4efc1dda7", 1, 41056, "", 0) \
    X("1.9.0", "cd57b23fa4bbad65", 1, 41062, "", 0) \
    X("XC3 1.0.0", "", 1, 0, "010074f013262000", 1)
