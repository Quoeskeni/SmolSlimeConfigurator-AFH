diff --git a/README.md b/README.md
index dd24cbd1faacd89e3d45d47c069f78002290c05f..a5a26a534ae2ed9c003ad6778c29c312ab3ca4f8 100644
--- a/README.md
+++ b/README.md
@@ -1,36 +1,37 @@
 # SmolSlimeConfigurator <img src="icon.png" width="32" height="32" alt="SmolSlimeConfiguratorICON">
 Pure Simple UI Configurator for SlimeVR Smol Slimes (Unofficial)
 
 
 <img width="1316" height="539" alt="newyes" src="https://github.com/user-attachments/assets/ce07f8ac-0857-42c3-9a02-f86d84e19fcc" />
 
 # Features
 
 - **Easy-to-use interface** — clean, modern, and simple to use & Helpful tooltips.
 - **Effortless configuration** — one-click buttons for calibration, pairing, and more.
 - **Automatic firmware updater** — just plug your tracker in via USB, select your firmware type, and flash the latest build instantly.
+- **AFH-first firmware source** — defaults to Quoeskeni AFH tracker/receiver builds that keep the shared discovery channel at channel 100 / 2500 MHz.
 - **Always up to date** — the firmware list automatically fetches the latest daily builds from GitHub.
 - **Custom firmware support** — flash your own `.uf2` or `.hex` files no problem.
 - **Favorites system** — star your most-used firmware versions by Right-Clicking (Middle-Clicking on Mac).
 - **Cross-platform** — available for **Windows**, **Linux**, **macOS**, and **Android**.
 - **Theme customization** — switch between **light/dark mode** and choose your favorite accent colour.
 
 # Download / install
 
 ## Option 1: download a ready-made executable
 
 Use the project [Releases](https://github.com/ICantMakeThings/SmolSlimeConfigurator/releases) page when you want the same install flow as the original app:
 
 - Windows: download `SmolSlimeConfigurator.exe`.
 - Linux: download `SmolSlimeConfigurator-linux`, then run `chmod +x SmolSlimeConfigurator-linux`.
 - macOS: download `SmolSlimeConfigurator-macos`, then allow it in Privacy & Security if Gatekeeper blocks a manually downloaded unsigned app.
 
 This repository also has a GitHub Actions workflow named **Build configurator binaries**. Maintainers can run it manually or publish a `v*` release/tag to build release artifacts automatically.
 
 ## Option 2: run from Python source
 
 ```bash
 python -m pip install customtkinter pyserial requests
 python SmolSlimeConfiguratorV9.py
 ```
 
@@ -38,50 +39,58 @@ python SmolSlimeConfiguratorV9.py
 
 Use Python 3.10 and run:
 
 ```bash
 python -m pip install customtkinter pyserial requests pyinstaller
 pyinstaller --onefile --windowed --name SmolSlimeConfigurator SmolSlimeConfiguratorV9.py
 ```
 
 The built file will appear in `dist/`. On Windows it will be `dist/SmolSlimeConfigurator.exe`.
 
 # Instructions
 **Note:** There is a [video tutorial](https://youtu.be/2PHelwy7Rcs) explaining general usage, and [this video](https://www.youtube.com/watch?v=ENINHh4L8tk) covers **Android usage** in detail.
 ## **First install**
 
 + Plug in the tracker or reciever, hold one side of a wire on rst pin ![image](https://github.com/user-attachments/assets/7cdaae27-21f9-428f-9327-d39bbf8dabc2) (4th pin down from where B+ pin is)
 and doubble tap gnd (usbc connector on the Nice!Nano)![image](https://github.com/user-attachments/assets/c1efbc20-bb2f-4fd8-9ecd-8869648ebf17)
 + Press "↻" refresh, then select the port from the dropdown menu on the left of the refresh button, then press "Connect"
 + Select the version of hardware from the dropdown menu called "Select Firmware", press "⬇ Firmware",  Wait ~20 seconds, the tracker will flash.
 
 ## **Pairing**
   
 + Plug in your Reciever, press "↻" refresh and select the port And then press "Connect"
 + To Configure your reciever, select the reciever tab, press pairing mode and power on each reciever one by one, you should notice ![image](https://github.com/user-attachments/assets/ab48dff0-e0f6-4113-a7f7-222260115964) the trackers being added, once all the trackers have been paired, press "Exit Pairing Mode"
 
 
+## **AFH firmware source**
+
+The configurator defaults to the Quoeskeni AFH CI firmware source (`Quoeskeni/SlimeNRF-Firmware-CI`) so receiver and tracker downloads come from matching AFH-enabled firmware builds. The AFH firmware forks keep SlimeVR compatibility on the firmware side and do not require changes to the standard SlimeVR server.
+
+The AFH discovery/pairing channel is channel `100`, which maps to 2500 MHz on nRF ESB. Keep the receiver and trackers on matching AFH builds before pairing.
+
+You can still switch to the upstream or backup firmware sources in **Settings → Firmware Source**, or provide a custom GitHub releases API URL.
+
 ## **AFH tools**
 
 AFH firmware builds expose two extra serial commands that are available from both the **Tracker** and **Receiver** tabs:
 
 + **AFH Info** sends `afh_info` and prints the current AFH channel, state, error counter, and epoch in the log.
 + **Force Channel 100** sends `afh_set_channel 100` to force the radio back to channel 100 / 2500 MHz, which is the expected AFH discovery/pairing channel for compatible firmware builds.
 
 If pairing does not start, connect the receiver and each tracker over USB, press **Force Channel 100**, then check **AFH Info** before entering pairing mode.
 
 Firmware note: `afh_info` and `afh_set_channel <ch>` must exist in the tracker/receiver firmware console. If `help` does not list those commands, update the AFH firmware first; the GUI can only send commands that the firmware knows how to execute.
 
 ### AFH pairing recovery checklist
 
 1. Flash the receiver and every tracker from matching AFH firmware builds.
 2. Connect the receiver over USB, press **Force Channel 100**, then press **AFH Info**.
 3. Enter **Pairing Mode** on the receiver.
 4. Power on one tracker at a time. If a tracker still has old pairing data, connect it over USB and press **Clear Con. Data** before pairing again.
 5. When all trackers are listed on the receiver, press **Exit Pairing Mode**.
 
 ## **Calibration**
 
 + Plug in a tracker, Press "↻" refresh, select the COM port & "Connect", press "Calibrate 6 Sides", do what the terminal says.
 + Then press "Calibrate", leave the tracker on a desk for 5~ seconds and done!
 
 **Note: You can also doubble tap the trackers button instead of pressing "Calibrate"**
