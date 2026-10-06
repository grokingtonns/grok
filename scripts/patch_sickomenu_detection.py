from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_sickomenu.py <SickoMenu source directory>")

root = Path(sys.argv[1]).resolve()

def replace_once(rel, old, new):
    path = root / rel
    text = path.read_text(encoding="utf-8")
    needle = old
    if needle not in text and needle.endswith("\n") and needle[:-1] in text:
        needle = needle[:-1]
    if needle not in text:
        raise RuntimeError(f"Expected source block not found in {rel}")
    text = text.replace(needle, new, 1)
    path.write_text(text, encoding="utf-8")
    print(f"patched {rel}")

# 1) Extend the Console's existing CHEAT event model with mod-client detections.
replace_once(
    "events/_events.h",
    """enum class CHEAT_ACTIONS {
\tCHEAT_TELEPORT,
\tCHEAT_KILL_IMPOSTOR
};""",
    """enum class CHEAT_ACTIONS {
\tCHEAT_TELEPORT,
\tCHEAT_KILL_IMPOSTOR,
\tCHEAT_SICKOMENU_USER,
\tCHEAT_SICKOMENU_PASSIVE,
\tCHEAT_MALUMMENU_PROBABLE
};"""
)

replace_once(
    "events/_events.h",
    """const std::vector<const char*> CHEAT_ACTION_NAMES = { "Teleporting", "Killed abnormally" };""",
    """const std::vector<const char*> CHEAT_ACTION_NAMES = {
\t"Teleporting",
\t"Killed abnormally",
\t"SickoMenu user (advertised/confirmed)",
\t"SickoMenu user (passive SickoChat signature)",
\t"MalumMenu user (probable v3.3.1 overload signature)"
};"""
)

# 2) Add a small console-event helper and make SickoChat itself a passive SickoMenu signature.
replace_once(
    "rpc/CustomRpcHandler.cpp",
    """std::string SafelyReadString(MessageReader* reader) {
\tint32_t pos = reader->fields._position, head = reader->fields.readHead;
\tint32_t num = MessageReader_ReadPackedInt32(reader, NULL);
\tbool hasString = MessageReader_get_BytesRemaining(reader, NULL) >= num;
\treader->fields._position = pos;
\treader->fields.readHead = head;

\treturn hasString ? convert_from_string(MessageReader_ReadString(reader, NULL)) : "";
}

void HandleRpc(PlayerControl* player, uint8_t callId, MessageReader* reader) {""",
    """std::string SafelyReadString(MessageReader* reader) {
\tint32_t pos = reader->fields._position, head = reader->fields.readHead;
\tint32_t num = MessageReader_ReadPackedInt32(reader, NULL);
\tbool hasString = MessageReader_get_BytesRemaining(reader, NULL) >= num;
\treader->fields._position = pos;
\treader->fields.readHead = head;

\treturn hasString ? convert_from_string(MessageReader_ReadString(reader, NULL)) : "";
}

static bool ModUserNameContains(uint8_t playerId, const std::string& needle) {
\tauto it = State.modUsers.find(playerId);
\treturn it != State.modUsers.end() && !it->second.empty() &&
\t\tit->second[0].find(needle) != std::string::npos;
}

static void AddModDetectionConsoleEvent(PlayerControl* player, CHEAT_ACTIONS action) {
\tif (player == nullptr || player == *Game::pLocalPlayer) return;
\tauto data = GetPlayerData(player);
\tif (data == nullptr) return;

\tsynchronized(Replay::replayEventMutex) {
\t\tState.liveConsoleEvents.emplace_back(
\t\t\tstd::make_unique<CheatDetectedEvent>(EVENT_PLAYER(data), action)
\t\t);
\t}
}

void HandleRpc(PlayerControl* player, uint8_t callId, MessageReader* reader) {"""
)

replace_once(
    "rpc/CustomRpcHandler.cpp",
    """\tif (callId == 101) {
\t\tif (State.PanicMode || !State.ReadAndSendSickoChat) return;

\t\tusing namespace std::chrono;""",
    """\tif (callId == 101) {
\t\t// SickoChat (RPC 101) is itself a SickoMenu-specific network signature.
\t\t// Detect it before honoring ReadAndSendSickoChat so hiding/disabling the
\t\t// visible RPC-420 advertisement does not also disable passive detection.
\t\tif (!State.PanicMode && player != *Game::pLocalPlayer && !ModUserNameContains(playerId, "SickoMenu")) {
\t\t\tState.modUsers[playerId] = {
\t\t\t\t"<#ff006c>SickoMenu</color>",
\t\t\t\t"<#fb0>passive</color>"
\t\t\t};
\t\t\tAddModDetectionConsoleEvent(player, CHEAT_ACTIONS::CHEAT_SICKOMENU_PASSIVE);
\t\t\tSTREAM_DEBUG("Passive SickoMenu signature (RPC 101) from " << ToString((Game::PlayerId)playerId));
\t\t\tif (State.SMAC_CheckSicko)
\t\t\t\tSMAC_OnCheatDetected(player, "SickoMenu User");
\t\t}

\t\tif (State.PanicMode || !State.ReadAndSendSickoChat) return;

\t\tusing namespace std::chrono;"""
)

# Let a later RPC 420 upgrade a passive Sicko entry to an advertised version.
replace_once(
    "rpc/CustomRpcHandler.cpp",
    """\tif (State.modUsers.find(playerId) != State.modUsers.end()) return;

\tswitch (callId) {""",
    """\tif (State.modUsers.find(playerId) != State.modUsers.end() && callId != (uint8_t)420) return;

\tswitch (callId) {"""
)

replace_once(
    "rpc/CustomRpcHandler.cpp",
    """\t\tif (State.modUsers.find(playerId) == State.modUsers.end() && MessageReader_get_BytesRemaining(reader, NULL) == 0) {
\t\t\tState.modUsers.insert({ playerId, { "<#ff006c>SickoMenu</color>", formattedVersion } });
\t\t\tSTREAM_DEBUG("RPC Received for another SickoMenu user from " << ToString((Game::PlayerId)playerId));
\t\t\tif (State.SMAC_CheckSicko) SMAC_OnCheatDetected(player, "SickoMenu User");
\t\t}""",
    """\t\tif (MessageReader_get_BytesRemaining(reader, NULL) == 0) {
\t\t\tbool alreadyAdvertised = ModUserNameContains(playerId, "SickoMenu") &&
\t\t\t\tState.modUsers.at(playerId).size() > 1 &&
\t\t\t\tState.modUsers.at(playerId)[1].find("passive") == std::string::npos;

\t\t\tState.modUsers[playerId] = { "<#ff006c>SickoMenu</color>", formattedVersion };
\t\t\tSTREAM_DEBUG("RPC Received for another SickoMenu user from " << ToString((Game::PlayerId)playerId));

\t\t\tif (!alreadyAdvertised)
\t\t\t\tAddModDetectionConsoleEvent(player, CHEAT_ACTIONS::CHEAT_SICKOMENU_USER);

\t\t\tif (State.SMAC_CheckSicko) SMAC_OnCheatDetected(player, "SickoMenu User");
\t\t}"""
)

# 3) Detect Malum v3.3.1's distinctive Overload() Pet-RPC payload/burst in PlayerPhysics.
replace_once(
    "hooks/PlayerPhysics.cpp",
    """#include "state.hpp"
#include "game.h"
""",
    """#include "state.hpp"
#include "game.h"
#include "utility.h"
#include "replay.hpp"
#include <chrono>
#include <unordered_map>
"""
)

replace_once(
    "hooks/PlayerPhysics.cpp",
    """void dPlayerPhysics_HandleRpc(PlayerPhysics* __this, uint8_t callId, MessageReader* reader, MethodInfo* method) {
\tif (State.ShowHookLogs) Log.HookDebug("Hook dPlayerPhysics_HandleRpc executed", false);
\tPlayerPhysics_HandleRpc(__this, callId, reader, method);
}
""",
    """namespace {
\tstruct MalumPetBurstState {
\t\tint32_t ownerId = -1;
\t\tint count = 0;
\t\tbool flagged = false;
\t\tstd::chrono::steady_clock::time_point windowStart = std::chrono::steady_clock::now();
\t};

\tstd::unordered_map<uint8_t, MalumPetBurstState> malumPetBursts;

\tbool IsMalumV331PetPayload(MessageReader* reader) {
\t\tif (reader == nullptr || MessageReader_get_BytesRemaining(reader, NULL) != 8)
\t\t\treturn false;

\t\tint32_t pos = reader->fields._position;
\t\tint32_t head = reader->fields.readHead;

\t\t// Two packed Vector2 values (4 ushorts). Malum v3.3.1's Overload()
\t\t// writes the second vector as raw ushort 0,0, which decodes off-screen.
\t\tMessageReader_ReadUInt16(reader, NULL);
\t\tMessageReader_ReadUInt16(reader, NULL);
\t\tuint16_t petX = MessageReader_ReadUInt16(reader, NULL);
\t\tuint16_t petY = MessageReader_ReadUInt16(reader, NULL);

\t\treader->fields._position = pos;
\t\treader->fields.readHead = head;

\t\treturn petX == 0 && petY == 0;
\t}

\tvoid AddMalumConsoleEvent(PlayerControl* player) {
\t\tif (player == nullptr || player == *Game::pLocalPlayer) return;
\t\tauto data = GetPlayerData(player);
\t\tif (data == nullptr) return;

\t\tsynchronized(Replay::replayEventMutex) {
\t\t\tState.liveConsoleEvents.emplace_back(
\t\t\t\tstd::make_unique<CheatDetectedEvent>(
\t\t\t\t\tEVENT_PLAYER(data),
\t\t\t\t\tCHEAT_ACTIONS::CHEAT_MALUMMENU_PROBABLE
\t\t\t\t)
\t\t\t);
\t\t}
\t}

\tvoid RegisterMalumPetSignature(PlayerPhysics* physics, MessageReader* reader) {
\t\tif (State.PanicMode || physics == nullptr || reader == nullptr) return;

\t\tauto player = physics->fields.myPlayer;
\t\tif (player == nullptr || player == *Game::pLocalPlayer) return;
\t\tif (!IsMalumV331PetPayload(reader)) return;

\t\tuint8_t playerId = player->fields.PlayerId;
\t\tauto now = std::chrono::steady_clock::now();
\t\tauto& state = malumPetBursts[playerId];

\t\t// Reset stale/reused PlayerIds and reset after the normal modUsers state is cleared.
\t\tif (state.ownerId != player->fields._.OwnerId ||
\t\t\t(state.flagged && State.modUsers.find(playerId) == State.modUsers.end())) {
\t\t\tstate = MalumPetBurstState{};
\t\t\tstate.ownerId = player->fields._.OwnerId;
\t\t\tstate.windowStart = now;
\t\t}

\t\tif (std::chrono::duration<float>(now - state.windowStart).count() > 0.70f) {
\t\t\tstate.count = 0;
\t\t\tstate.windowStart = now;
\t\t}

\t\tstate.count++;

\t\t// Normal petting is one RPC. Malum's Overload packs bursts of these special
\t\t// zero-pet-position RPCs; require six in 700ms before assigning the label.
\t\tif (!state.flagged && state.count >= 6) {
\t\t\tstate.flagged = true;

\t\t\t// A confirmed Sicko signature takes precedence over a heuristic Malum label.
\t\t\tauto existing = State.modUsers.find(playerId);
\t\t\tbool confirmedSicko = existing != State.modUsers.end() &&
\t\t\t\t!existing->second.empty() &&
\t\t\t\texisting->second[0].find("SickoMenu") != std::string::npos;

\t\t\tif (!confirmedSicko) {
\t\t\t\tState.modUsers[playerId] = {
\t\t\t\t\t"<#b56cff>MalumMenu</color>",
\t\t\t\t\t"<#ffb347>probable v3.3.1</color>"
\t\t\t\t};
\t\t\t}

\t\t\tAddMalumConsoleEvent(player);
\t\t\tSTREAM_DEBUG("Probable MalumMenu v3.3.1 overload signature from " << ToString((Game::PlayerId)playerId));

\t\t\tif (State.SMAC_CheckOtherCheats)
\t\t\t\tSMAC_OnCheatDetected(player, "MalumMenu User");
\t\t}
\t}
}

void dPlayerPhysics_HandleRpc(PlayerPhysics* __this, uint8_t callId, MessageReader* reader, MethodInfo* method) {
\tif (State.ShowHookLogs) Log.HookDebug("Hook dPlayerPhysics_HandleRpc executed", false);

\tif (callId == (uint8_t)RpcCalls__Enum::Pet) {
\t\ttry {
\t\t\tRegisterMalumPetSignature(__this, reader);
\t\t}
\t\tcatch (...) {
\t\t\tLOG_ERROR("Exception occurred in passive MalumMenu detection (PlayerPhysics)");
\t\t}
\t}

\tPlayerPhysics_HandleRpc(__this, callId, reader, method);
}
"""
)

# 4) Put Malum into the existing SMAC "Known Cheat Usage" category so the Console/
#    detection settings treat it alongside the other known menus.
replace_once(
    "user/utility.cpp",
    """{ "Known Cheat Usage", { "AmongUsMenu User", "ChocooMenu User", "KillNetwork User", "SlopMenuCrew User" } },""",
    """{ "Known Cheat Usage", { "AmongUsMenu User", "ChocooMenu User", "KillNetwork User", "SlopMenuCrew User", "MalumMenu User" } },"""
)

replace_once(
    "user/utility.cpp",
    """        { "SlopMenuCrew User", "Known Cheat Usage" },
        { "Abnormal Name", "Abnormal Names" },""",
    """        { "SlopMenuCrew User", "Known Cheat Usage" },
        { "MalumMenu User", "Known Cheat Usage" },
        { "Abnormal Name", "Abnormal Names" },"""
)

print("Passive SickoMenu + MalumMenu detection patch applied successfully.")

# Build trigger: passive detection pack
