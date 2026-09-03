# Tracking the "biomass release" / external enable contact (Kesselfreigabe) over Modbus

Research note for `dbus-froeling` (Fröling T4e / Lambdatronic 3200, Modbus over TCP).

Date: 2026-09-03

---

## Answer

**Qualified yes — readable, not writable.**

Fröling's own Modbus specification for the Lambdatronic 3200 exposes the external
enable/release contact as **digital input ID `10004`, named "Kesselfreigabe"** (boiler
release). It is read with **Read Input Status / Read Discrete Inputs (FC = 02)**, at
**wire offset 3** (`10004 − 10001`). That is exactly the "externer Kontakt / Freigabekontakt /
Freigabe extern" input on terminal **KM-14** of the Kernmodul — the potential-free external
release-or-start contact.

**Confirmed on the hardware** (2026-09-03): `10004` was observed reading `0` with the release
disabled and `1` after it was enabled, while `10001`–`10003` held steady. Polarity is
**active high** — `1` = contact closed = release granted. See
[Measured results](#measured-results-on-this-boiler).

It is **read-only**. Fröling documents the digital-input range for reading only (FC = 02);
no write-coil function (FC = 05/15) and no writable holding register for the boiler release
appear anywhere in the specification. The commissioning parameter that decides what the
contact *means* ("Wie wird der Kesselfreigabe-Kontakt am Kernmodul verwendet" /
"Kesselfreigabe-Eingang vorhanden") is **not in the Modbus parameter list at all**, so you
cannot even read how the input is configured — only whether the contact is currently
made. Fröling has no register called "Biomasse-Freigabe"; "Kesselfreigabe" is the term
their firmware and manuals use for this input.

If the goal is to *command* the boiler rather than observe it, the documented Modbus levers
are different registers (external power demand, heating-circuit release, DHW setpoints) —
see [Writable alternatives](#writable-alternatives-if-you-want-to-command-not-observe).

---

## Evidence

### 1. What controller and protocol this repo actually speaks

| Fact | Where |
| --- | --- |
| Fröling T4e, Modbus TCP, port 502, slave/device ID 2 | `README.md:3`, `README.md:70-74`; `froeling_status.py:14-16` |
| Addressing is Fröling's "Variante 1" offset form — the register number minus the range base | `dbus-froeling.py:42-47` (`# Modbus register definitions (offsets from 30001)`) |
| Reads use `read_input_registers` (FC = 04) only | `dbus-froeling.py:391-395`, `dbus-froeling.py:416-420` |
| Registers currently used: 30001 boiler flow, 32001/32003 buffer top/bottom, 34001 Anlagenzustand, 34002 Kesselzustand | `dbus-froeling.py:43-47` |
| Vendor spec is vendored into the repo | `B1200522_ModBus Lambdatronic 3200_50-04_05-19_de.pdf` (repo root), added in commit `38081af` "Include Froeling documentation" |

So the repo currently touches only two of the six Fröling address ranges (aktuelle Werte and
Anlagen-/Kesselzustand). Digital inputs are simply not implemented yet — there is no code or
comment about them anywhere (`grep -ri "freigabe\|discrete\|digital" *.py` returns nothing
relevant).

The vendored PDF is **Fröling's own document, B1200522, "Kommunikationsprotokoll ModBus
Lambdatronic 3200", V 50.04 − B 05.19, dated 19.01.2022** — i.e. a first-party primary source,
and the newest publicly available revision (see [Open questions](#open-questions)).

### 2. The first-party register: digital input 10004 "Kesselfreigabe"

From the vendored Fröling spec, **§3.2 "Digitale Eingänge", page 9**:

```
3.2 Digitale Eingänge
Folgende Tabelle zeigt alle verfügbaren digitalen Eingänge.

  ID       BESCHREIBUNG
10001   Türkontaktschalter
10002   STB Eingang
10003   NOT-AUS Eingang
10004   Kesselfreigabe
```

— `B1200522_ModBus Lambdatronic 3200_50-04_05-19_de.pdf`, §3.2, p. 9.

And the access method, **§2.3 "Digitale Eingänge", page 5**:

```
2.3 Digitale Eingänge
Es können alle in der Liste angeführten digitalen Eingänge gelesen werden.
 ▪ Funktion: Read Input Status (FC=02)
 ▪ Adressbereich: 10001-10004
```

— same PDF, §2.3, p. 5. Note the wording: *"gelesen werden"* — read, only. Compare with
§2.5, which explicitly grants write access to a subset of parameters ("alle mit „R/W"
vermerkten Parameter geschrieben werden", FC = 06). No such clause exists for digital inputs,
and the digital-input table has no R/W column at all.

The same table with the same IDs appears in the older revision **B 05.14 (24.05.2017)**, §3.2,
confirming this is stable across firmware generations:
<https://community.symcon.de/uploads/short-url/pKEcnNcXuxRf57vBir27I2UZhKZ.pdf>
(and revision B 05.17: <https://forum.iobroker.net/assets/uploads/files/1577795130910-b1200419_modbus-lambdatronic-3200_50-04_05-17_de.pdf>).

Addressing: this repo's convention (`dbus-froeling.py:42`) is Fröling's Variante 1 — subtract
the range base. For digital inputs that base is 10001, so **Kesselfreigabe = offset 3**.

### 3. What "Kesselfreigabe" is, in Fröling's own words

From Fröling's service manual for the H 3200 (the Lambdatronic variant used on
Hackschnitzel-/Pellets boilers, i.e. the T4/T4e family), **§2.1.5 "Kesselfreigabe-Kontakt"**:

> Bei Inbetriebnahme des Kessels mit dem Einstellungsassistenten wird die Funktion des
> Kesselfreigabe-Kontaktes („Wie wird der Kesselfreigabe-Kontakt am Kernmodul verwendet") für
> die optionale Auswertung eines **externen, potentialfreien Freigabe- bzw. Startkontaktes**
> abgefragt.

Three configurable behaviours, quoted from the same section:

| Einstellung | Beschreibung (verbatim) |
| --- | --- |
| **nicht verwendet** | "Keine Auswirkung auf Kesselbetrieb (Kontakt darf nicht gebügelt/gebrückt werden)." |
| **Kessel freigeben / sperren** | "Solange der Kesselfreigabe-Kontakt geschlossen ist, regelt die Kesselregelung nach den einstellten Parametern (Betriebsart, Zeitfenster, …). Wird der Kesselfreigabe-Kontakt geöffnet, verliert der Kessel die Freigabe und stellt kontrolliert ab. Solange der Kesselfreigabe-Kontakt geöffnet ist, werden Heizanforderungen ignoriert (z.B. Abgasthermostat eines Beistellkessels, Hausanschlussbox)." |
| **Extraheizen** | "Solange der Kesselfreigabe-Kontakt geöffnet ist, regelt die Kesselregelung nach den eingestellten Parametern. Wird der Kesselfreigabe-Kontakt geschlossen, startet der Kessel im Dauerlastbetrieb (z.B. Wärmeanforderung eines Heizlüfters)." |

— *Servicehandbuch Lambdatronic H 3200 für Hackschnitzel- und Pelletskessel*, B1480822_de,
§2.1.5, p. 11: <https://www.tsd.lu/files/82257.pdf>

The physical terminal is **KM-14 "Kesselfreigabe"** on the Kernmodul, wiring `2 × 0.75 mm²`
(same manual, §2.1 terminal table, p. ~10). Identical wording appears in the P 3200 service
manual for pellet boilers, §2.1.5:
<https://img.colons.de/article_documents/Daten/DAM-Bilder/99153255/2205/301/301262/pdf/0/B1440720_Lambdatronic_P_3200_Pelletskessel_Touchbedienger%C3%A4t_de.pdf>
and is summarised on ManualsLib for the SP 3200 as "Kesselfreigabe-Eingang":
<https://www.manualslib.de/manual/535470/Froling-Lambdatronic-Sp3200.html?page=10>

**Consequence for interpreting the bit:** what `10004 = 1` *means* depends on the
commissioning setting above, and that setting is not exposed over Modbus (see §5). Under
"Kessel freigeben/sperren", contact closed = boiler released. Under "Extraheizen", contact
closed = forced continuous-load. Under "nicht verwendet", the bit is cosmetic.

### 4. Independent implementation confirming this reading

The Home Assistant integration `ha_froeling_lambdatronic_modbus` implements exactly this and
treats it as read-only. Treat as secondary evidence — but note it cites and vendors the *same*
Fröling PDF, byte-for-byte identical to the copy in this repo (verified: both files
`md5 = 9ccf261cfe801090bbb279118c7cda68`).

```python
"kesselfreigabe": {
    "discrete_input": 10004,
    "type": "binary_sensor"
},
```
— `custom_components/froeling_lambdatronic_modbus/entity_definitions.py`,
<https://github.com/GyroGearl00se/ha_froeling_lambdatronic_modbus>

And the offset convention, which matches this repo's:

```python
result = await self.controller.async_read_discrete_inputs(
    discrete_input_address - 10001, 1
)
```
— `coordinator.py` in the same repo. Its writer (`async_write_register`, FC = 06) is used only
for holding registers; there is no coil-write path, and `kesselfreigabe` is a `binary_sensor`,
never a `switch`.

### 5. Why it is not writable, and what is *not* exposed

* **No write function for digital inputs.** The spec lists FC = 01 (read coils, §2.2), FC = 02
  (read discrete inputs, §2.3), FC = 04 (read input registers, §2.4), FC = 03/06 (read/write
  holding registers, §2.5). FC = 05 and FC = 15 (Write Coil) are absent from the document
  entirely. §2.1 also notes that attempting an unsupported function returns Modbus exception
  01 "Illegal Function".
* **The configuration parameter is absent from the Modbus map.** Searching the whole vendored
  spec for "Kesselfreigabe" yields exactly one hit — the digital-input table entry. Neither
  "Kesselfreigabe-Eingang vorhanden" nor "Wie wird der Kesselfreigabe-Kontakt … verwendet"
  appears in §3.4 "Parameter" (40001–43030). So you cannot read or change how the input is
  wired up, over Modbus.
* **No coil for it either.** §3.1 "Digitale Ausgänge" (readable via FC = 01) lists only
  `0 Störmeldung`, `1 Störmeldekontakt`, and `1000…1540 Heizkreispumpe 0-18` — nothing
  boiler-release-shaped.
* **No "Biomasse" anything.** Grepping the spec for `Biomasse` returns zero hits. If the user's
  installation calls the contact "Biomasse-Freigabe", that is either installer/hydraulic-schematic
  labelling or a third-party (heat-pump / hybrid / district-heating "Hausanschlussbox")
  controller's name for the contact it drives. On the Fröling side it lands on KM-14 and reads
  back as `10004 Kesselfreigabe`.

### Writable alternatives, if you want to command not observe

These *are* documented as writable, and are the sanctioned ways to make the boiler run from
outside. None of them is the release contact; they act *in addition to* it (the release contact,
if configured, must still be closed).

| What | Register(s) | Access | Source |
| --- | --- | --- | --- |
| **Externe Leistungsanforderung over Modbus** — the closest thing to "release the biomass boiler from outside". Set parameter "Quelle für ext. Leistungsanf. (0 – Aus, 1 – 0-10V, 2 – Modbus)" to 2, then transmit percent values; >35 % starts the boiler in Dauerlastbetrieb, <30 % shuts it down. | `40480` Quelle für externe Leistungsanforderung (min 0 / max 2) — **but the spec marks it `R`, read-only.** Feedback: `30114` "Eingang externe Leistungsanforderung" (%), `30115` "Aktuelle externe Leistungsanforderung" (%), both FC = 04 read-only. | see caveat | vendored PDF §3.4 p. 28 (40480/40481), §3.3 p. 11 (30114/30115); behaviour: H 3200 manual "Externe Leistungsanforderung", p. 27, <https://www.tsd.lu/files/82257.pdf> |
| **Freigabe Heizkreis 1-18** — release/block heating circuits | `48029 – 48046`, values 0/1 | **write FC = 06**, read FC = 03 | vendored PDF §3.5 p. 48 |
| **Betriebsart Heizkreis 1-18** (0 Aus / 1 Automatik / 2 Extraheizen / 3 Absenken / 4 Dauerabsenken / 5 Partybetrieb) | `48047 – 48064` | **write FC = 06** | vendored PDF §3.5 p. 48 |
| **Vorlauf-Solltemperatur HK 1-18** / **Boiler-Solltemperatur 1-8** — fabricate a heat demand | `48001 – 48018` / `48019 – 48026`, scale 2 | **write FC = 06** | vendored PDF §3.5 p. 48, §2.6 p. 6 |
| Boiler/system state you already read | `34001` Anlagenzustand, `34002` Kesselzustand | read FC = 04 | `dbus-froeling.py:46-47`; vendored PDF §3.7 p. 60 |
| **Kesselanforderung über Heizkreis oder Boiler steht an** — is a heat demand pending? A useful companion signal to the release contact. | `30057` | read FC = 04 | vendored PDF §3.3 p. 10 |

Two important caveats on the writable set:

1. **Writing anything requires the 2014 protocol.** Fröling: *"HINWEIS! Schreiben von Parametern
   ist nur mit Protokoll 2014 möglich!"* — you must set, at the boiler keypad,
   `Anlage ⇒ Einstellen ⇒ Allg. Einst ⇒ MODBUS Einstellungen ⇒ "MODBUS Protokoll 2014
   verwenden" = JA` (and `"COM 2 wird als MODBUS Schnittstelle verwendet" = JA`).
   Otherwise every write returns exception 01 "Illegal Function". Vendored PDF §1.2 p. 3,
   §1.4.3 p. 4, §2.5 p. 6.
2. **The Kesselfernsteuerung registers time out and rate-limit.** If none of the 48xxx registers
   is written for more than two minutes, the external setpoint override deactivates and the
   controller reverts to its own heating curve. There is also a 10-minute minimum switching
   interval; a too-soon change is ignored and the reply carries `-1` instead of the written
   value. Vendored PDF §2.6 pp. 6-7.
3. **The external-power-demand source register is marked read-only.** `40480` carries `R`, not
   `R/W`, in the vendored spec — so per the document you must set
   "Quelle für ext. Leistungsanf." = 2 (Modbus) **at the boiler keypad**, in
   `Kessel ⇒ Allgemeine Einstellungen`. And the spec does not document *which* register you then
   write the percent value to. This is the biggest genuine gap in the documentation — see
   [Open questions](#open-questions).

---

## How to verify on your hardware

All of this is cheap to check and non-destructive: reading discrete inputs cannot change
anything on the boiler.

### 1. Read the bit with mbpoll

`README.md:200-204` already documents installing `mbpoll` on Venus OS. Digital inputs are
`-t 1`. Watch the addressing base: **mbpoll's `-r` is 1-based by default**, so use `-0` to make
it match the offsets used in `dbus-froeling.py`.

```bash
opkg update && opkg install mbpoll

# Kesselfreigabe, discrete input, Fröling offset 3 (= register 10004)
mbpoll 192.168.1.245 -p 502 -a 2 -0 -t 1 -r 3 -c 1

# Or read all four digital inputs at once (Türkontakt, STB, NOT-AUS, Kesselfreigabe)
mbpoll 192.168.1.245 -p 502 -a 2 -0 -t 1 -r 0 -c 4
```

(Without `-0`, add one: `-t 1 -r 4`. The existing example in `README.md:204` uses
`-t 3 -r 2000` for buffer-top, which is off by one against `BUFFER_TEMP_TOP = 2000` in
`dbus-froeling.py:44` for the same reason — worth fixing while you are in there.)

### 2. Read it from Python, matching this repo's style

`pymodbus` 2.5.3 as shipped in Venus OS, same `unit=` convention as `dbus-froeling.py:394`:

```python
# offsets from 10001
KESSELFREIGABE = 3      # register 10004: external boiler release contact

result = client.read_discrete_inputs(KESSELFREIGABE, count=1, unit=FROELING_DEVICE_ID)
if not result.isError():
    released = bool(result.bits[0])
```

Note this needs a **new** read helper — `read_temperature`/`read_status` in
`dbus-froeling.py:385-430` both call `read_input_registers` (FC = 04) and unpack
`result.registers`, whereas FC = 02 returns `result.bits`.

### 3. Establish the polarity empirically

Done — see [Measured results](#measured-results-on-this-boiler) below. Polarity is active high.
The method, if it needs repeating: open the external contact (or pull the KM-14 link) and
re-read, then close it and re-read; the bit that flips is your answer. `10001
Türkontaktschalter` is the easiest input to toggle deliberately (open the boiler door) and
gives a known-good reference for the whole block. Losing release should also make `34002` walk
through the "Abstellen …" states (10–14) toward `1 Kessel Aus`, per §3.7.2.

### 4. Confirm how the contact is configured (must be done at the boiler)

Because the configuration is not on Modbus, check it on the keypad. In the
Kesselfreigabe-Kontakt commissioning question, confirm which of the three options is active:
`nicht verwendet` / `Kessel freigeben / sperren` / `Extraheizen`. Also verify the parameter
`"Kesselfreigabe-Eingang vorhanden" = JA`. Until you know this, the bit's meaning is ambiguous
(see §3 above).

### 5. Dump the full parameter list from your own controller

If you suspect your firmware exposes more than the 2022 document lists, enumerate it rather than
guess. Per §2.1 of the spec, reading a register that is *inside* a valid range but *not* in the
published list returns **`-1` (0xFFFF)** rather than a Modbus exception — which makes a sweep
safe and self-describing:

```bash
# sweep the parameter range in blocks (max 122 registers per request, §2.5)
for r in $(seq 0 122 3029); do
  mbpoll 192.168.1.245 -p 502 -a 2 -0 -t 4 -r $r -c 122 -1
done
```

Anything that comes back as something other than `-1`/`65535` exists on your controller. Do the
same over `-t 3` (input registers, offsets 0–2624) and `-t 1 -r 0 -c 4` (discrete inputs).
Use `-t 4` (holding) reads only — do **not** sweep with writes.

---

## Measured results on this boiler

Read directly over Modbus TCP (192.168.1.245:502, unit ID 2, FC 02) on 2026-09-03, with the
release toggled between the two reads:

| ID | Offset | Name | Release disabled | Release enabled |
|----|--------|------|------------------|-----------------|
| `10001` | 0 | Türkontaktschalter | `0` | `0` |
| `10002` | 1 | — | `0` | `0` |
| `10003` | 2 | — | `0` | `0` |
| `10004` | 3 | **Kesselfreigabe** | **`0`** | **`1`** |
| `10005`+ | 4+ | — | exception 2 (illegal data address) | exception 2 |

Three things this settles that the specification does not:

1. **The offset convention is confirmed**: `wire offset = ID − 10001`.
2. **The discrete-input space is exactly four wide.** Offset 4 and up return Modbus exception 2.
   Offsets 0–3 can be read in a single FC 02 request with quantity 1–4; quantities above 4 fail
   because the range ends, not because multi-reads are unsupported.
3. **Polarity is active high.** `0` = contact open = release withheld; `1` = contact closed =
   release granted. The other three inputs did not move, which isolates the change to `10004`
   and independently confirms the register identification.

Still not knowable over Modbus: *how the contact is configured*. `1` means the contact is made;
whether the controller treats that as "Kessel freigeben / sperren" or "Extraheizen" is a keypad
setting absent from the Modbus map (see §5 and step 4 above).

---

## How this is published to Venus OS / VRM

Implemented in `dbus-froeling.py` as `BoilerReleaseContact`
(`com.victronenergy.digitalinput.froeling_release`, device instance 104), a subclass of the
`DigitalInput` base class that holds the shared housekeeping — service and settings creation,
the mandatory and digital-input paths, and the `/State` and `/Alarm` arithmetic. Subclasses
supply only `TYPE_ID`, `TRANSLATION` and their own update logic.
`BoilerOperatingContact` derives from the same base, which is how it acquired the `/InputState`,
`/Alarm` and `/Settings/*` paths it was previously missing.

**`/Type` = 3 (Bilge pump), `/State` = 2 (Off) / 3 (On).** Type 3's canonical translation in
Victron's own `dbus-digitalinputs` is `off/on`, so this is a *conventional* type/state pairing
rather than a mismatched one:

```python
class BilgePump(PinAlarm):
    _product_name = "Bilge pump"
    type_id = 3
    translation = 1 # off, on
```

`/State` is computed the same way Victron does it — `2 * translation + (level ^
InvertTranslation)` — so `level 1` (released) yields `3` = "On" with no inversion needed.
`/CustomName` is set to "Boiler Release", so the string "Bilge pump" appears nowhere a user
looks except the device page's Type row.

### Why not the other candidate types

* **`/Type` = 9 (Generator)** — already used by `froeling_operating`, and in real
  `dbus-digitalinputs` type 9 has side effects: it pushes `RemoteGeneratorSelected` into every
  `com.victronenergy.vebus.*` service and `/DigitalInput/*` into `generator.startstop0`.
* **`/Type` = 10 (Generic I/O)** — renders, but incompletely. `gui-v2` selects its delegate by
  *service class*, not by `/Type` (`pages/settings/devicelist/DeviceListPage.qml:33`), so the
  device still appears in the list and `/State` 0/1 still renders as "Low"/"High". But
  `digitalInput_typeToText` has no case for 10 (`src/enums.cpp:300-339`; `src/enums.h:738`
  comments `// 10 is not used`), so the device page's Type row is blank. `gui-v2` contains no
  occurrence of `GenericIO` at all, and `dbus_modbustcp/attributes.csv` enumerates only types
  2–9.
* **`/Type` = 2 (Door alarm) with off/on states** — same rendered labels as type 3, but a
  mismatched pair. Since VRM does its own state-to-text mapping (see below), that adds risk for
  no gain. Type 2 with its own `open/closed` pair (states 6/7) is the alternative worth keeping
  in mind: it is the only variant whose alarm capability Victron documents explicitly.

### Type and state are not coupled in the GUI

Worth recording, because it is not obvious: nothing downstream enforces the conventional
pairing. `/State`'s gettext in `dbus-digitalinputs` is `lambda p, v: TRANSLATIONS[v//2][v%2]`
— a function of the state value alone. In `gui-v2`, `digitalInput_stateToText(state)` and
`digitalInput_typeToText(type)` are two independent switch statements (`src/enums.cpp:341` and
`:300`) called independently from QML. `dbus_modbustcp/attributes.csv` gives `/Type` and
`/Alarm` enum text but `/State` none. So any type/state combination renders; the pairing is a
producer-side convention in `dbus-digitalinputs` class attributes.

### Paths published

The full `PinAlarm` shape from `dbus-digitalinputs`, so the GX GUI, the Venus Modbus TCP server
and VRM all see what they expect:

```
/ProductId       41318 (0xA166)   # PinAlarm.product_id
/Type            3
/InputState      0|1              # raw bit, invalid until the first read
/State           2|3              # Off|On, invalid until the first read
/Alarm           0                # alarm not used
/Count           0                # not used; the GX GUI does not display it
/CustomName      "Boiler Release"  # writeable, persisted
/Settings/AlarmSetting            # writeable
/Settings/InvertTranslation       # writeable
/Settings/InvertAlarm             # writeable
```

`/InputState` and `/State` are published as invalid (`None`) until the first successful poll.
Publishing a placeholder level instead would assert a state that has not been measured, and
because `/State` is `2 * TRANSLATION + level`, the placeholder for the operating contact's
Running/Stopped translation is `10` — "Running". Subscribers see that correct itself to `11`
one poll later, which reads as the boiler having lit and gone out. For the same reason a failed
read holds the last known state and clears `/Connected`, rather than asserting "stopped".

`/Count` is part of the `PinAlarm` shape and is published as a constant `0`. The GX GUI has no
display for it, so counting edges would only be state that resets on restart and is read by
nobody.

The three `/Settings/*` paths are published because `gui-v2`'s
`pages/settings/devicelist/PageDigitalInput.qml` binds `ListSwitch` items directly to them,
unconditionally for every type; without them the device's Setup page shows dead switches.
`InvertTranslation` is honoured in the state computation, so the Off/On sense can be flipped
from the GUI without a code change.

**No alarm is configured.** `/Settings/AlarmSetting` defaults to `0`, so `/Alarm` stays `0`.
The machinery is present (`/Alarm` and `get_alarm_state` live on the `PinAlarm` base class that
every type inherits) should it be wanted later; `InvertAlarm = 1` would make "release withdrawn"
the alarm condition.

---

## Open questions / remaining uncertainty

1. **Which register carries the Modbus external power demand?** The H 3200 and P 3200 service
   manuals both say *"Bei Leistungsanforderung über Modbus werden direkt die Prozentwerte
   übermittelt"* (<https://www.tsd.lu/files/82257.pdf>, p. 27) — but the B 05.19 Modbus spec
   documents no writable register for that percentage. §3.5 Kesselfernsteuerung jumps from
   `48019–48026` to `48029–48046`, leaving **`48027` and `48028` unlisted** — a suspicious gap,
   but that is my inference, not documented, and I could not confirm it from any first-party
   source. Also unresolved: `40480` "Quelle für externe Leistungsanforderung" is marked `R` in
   the spec although it is a settable menu parameter, so the spec's R/W column may be
   conservative or stale. **If commanding the boiler is the actual goal, ask Fröling support
   directly for the external-power-demand write register** — this is the one question the public
   documentation does not answer.
2. ~~**Bit polarity of `10004`** is undocumented~~ — **resolved by experiment 2026-09-03**:
   active high, `1` = contact closed = release granted. See
   [Measured results](#measured-results-on-this-boiler).
3. **Firmware revision.** The vendored spec is V 50.04 − B 05.19 and is the newest revision I
   could find published (revisions found: B 05.14 / 2017, B 05.17 / 2019, B 05.19 / 2022;
   nothing newer, and froeling.com's public download area does not list the Modbus protocol
   document at all — it appears to circulate via dealers and forums). If your T4e runs a newer
   build, its register list may differ; the parameter sweep in step 5 is the way to find out.
4. **Term mismatch.** I found no Fröling document, in German or English, using
   "Biomasse-Freigabe" / "Freigabe Biomasse" as a register or parameter name. If that label came
   from a hydraulic schematic, a heat-pump controller, or a district-heating Hausanschlussbox,
   it is worth confirming that the contact it drives is physically wired to KM-14 on the
   Kernmodul before assuming `10004` reflects it. If it is wired somewhere else entirely — e.g.
   to a Digitalmodul input, or to the Analogmodul input used for external power demand — then
   `10004` is the wrong register and the state would have to be inferred from `30114`
   (Eingang externe Leistungsanforderung) instead.
5. **Multi-boiler / cascade setups.** `10001–10004` are the Kernmodul's own inputs. For a
   cascade there is `30503` "Betriebsstunden von Kessel 2 (Brennerkontakt)" and `40501`
   "Welcher zweite Kessel ist vorhanden?", but I found no per-boiler release inputs. Not
   investigated further, as this repo targets a single boiler.

---

## Sources

**First-party (Fröling):**
* `B1200522_ModBus Lambdatronic 3200_50-04_05-19_de.pdf` — *Kommunikationsprotokoll ModBus
  Lambdatronic 3200*, V 50.04 − B 05.19, 19.01.2022. Vendored in this repo's root. Public copy:
  <https://www.holzheizer-forum.de/attachment/37208-b1200522-modbus-lambdatronic-3200-50-04-05-19-de-1-pdf/>
* Earlier revisions, for cross-checking stability of the digital-input table:
  B 05.14 <https://community.symcon.de/uploads/short-url/pKEcnNcXuxRf57vBir27I2UZhKZ.pdf> ·
  B 05.17 <https://forum.iobroker.net/assets/uploads/files/1577795130910-b1200419_modbus-lambdatronic-3200_50-04_05-17_de.pdf>
* *Servicehandbuch Lambdatronic H 3200 für Hackschnitzel- und Pelletskessel*, B1480822_de —
  <https://www.tsd.lu/files/82257.pdf> (§2.1.5 Kesselfreigabe-Kontakt p. 11; Externe
  Leistungsanforderung p. 27; Kessel – Allgemeine Einstellungen p. 67)
* *Servicehandbuch Lambdatronic P 3200 für Pelletskessel*, B1440720_de —
  <https://img.colons.de/article_documents/Daten/DAM-Bilder/99153255/2205/301/301262/pdf/0/B1440720_Lambdatronic_P_3200_Pelletskessel_Touchbedienger%C3%A4t_de.pdf>
* *Bedienungsanleitung Lambdatronic SP 3200* (Kesselfreigabe-Eingang), via ManualsLib —
  <https://www.manualslib.de/manual/535470/Froling-Lambdatronic-Sp3200.html?page=10>

**Secondary (third-party implementations):**
* `GyroGearl00se/ha_froeling_lambdatronic_modbus` — Home Assistant integration;
  `kesselfreigabe` as read-only `binary_sensor` on `discrete_input: 10004` —
  <https://github.com/GyroGearl00se/ha_froeling_lambdatronic_modbus>

**This repo:**
* `README.md`, `dbus-froeling.py:42-47`, `dbus-froeling.py:385-430`, `froeling_status.py:14-22`
