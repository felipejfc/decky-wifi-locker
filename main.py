import os
import json
import subprocess
import shutil
import asyncio
from pathlib import Path
from typing import TypedDict
import decky

class PluginSettings(TypedDict):
    auto_lock_on_startup: bool

class Plugin:
    # State to track if WiFi is currently locked
    wifi_locked = False
    current_ssid = None
    current_bssid = None
    
    # Path to the scripts
    lock_script_path = os.path.join(decky.DECKY_PLUGIN_DIR, "assets", "lock_wifi.sh")
    unlock_script_path = os.path.join(decky.DECKY_PLUGIN_DIR, "assets", "unlock_wifi.sh")
    state_file_path = os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "wifi_lock_state.json")
    settings_file_path: Path = Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / "wifi_locker_settings.json"

    def _load_settings(self) -> PluginSettings:
        """Load plugin settings from disk, returning defaults if absent or malformed."""
        try:
            if self.settings_file_path.exists():
                return json.loads(self.settings_file_path.read_text())
        except Exception as e:
            decky.logger.error(f"Error reading settings file: {e}")
        return {"auto_lock_on_startup": False}

    def _save_settings(self, data: PluginSettings) -> None:
        """Persist plugin settings to disk."""
        try:
            self.settings_file_path.parent.mkdir(parents=True, exist_ok=True)
            _ = self.settings_file_path.write_text(json.dumps(dict(data)))
        except Exception as e:
            decky.logger.error(f"Error saving settings file: {e}")

    def _get_clean_env(self):
        """Get environment with cleared LD_LIBRARY_PATH to fix decky-loader subprocess issues"""
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = ""

        return env 
    
    # Lock WiFi to current BSSID
    async def lock_wifi(self) -> dict[str, object]:
        if self.wifi_locked:
            return {"success": False, "message": "WiFi already locked", "ssid": self.current_ssid, "bssid": self.current_bssid}
        
        try:
            decky.logger.info("Locking WiFi to current BSSID")
            result = subprocess.run([self.lock_script_path], capture_output=True, text=True, env=self._get_clean_env())
            decky.logger.info(f"Lock script exit code: {result.returncode}")
            decky.logger.info(f"Lock script stdout: {result.stdout}")
            
            if result.stderr:
                decky.logger.error(f"Lock script stderr: {result.stderr}")
            
            if result.returncode == 0:
                # Parse the JSON output from the script
                try:
                    output_data = json.loads(result.stdout.strip())
                    self.current_ssid = output_data.get("ssid")
                    self.current_bssid = output_data.get("bssid")
                    script_success = output_data.get("success", False)
                    
                    # Log raw stdout and stderr for debugging if needed
                    decky.logger.info(f"Raw script output: {result.stdout}")
                    if result.stderr:
                        decky.logger.error(f"Script stderr: {result.stderr}")
                    
                    if script_success:
                        self.wifi_locked = True
                        decky.logger.info(f"WiFi locked to SSID: {self.current_ssid}, BSSID: {self.current_bssid}")
                        
                        # Save state to file
                        try:
                            state_data = {
                                'locked': True,
                                'ssid': self.current_ssid,
                                'bssid': self.current_bssid
                            }
                            with open(self.state_file_path, 'w') as f:
                                json.dump(state_data, f)
                            decky.logger.info(f"Saved lock state to {self.state_file_path}")
                        except Exception as e:
                             decky.logger.error(f"Error saving state file: {e}")
                             # Even if saving fails, proceed but log the error

                        return {
                            "success": True, 
                            "message": f"WiFi locked to {self.current_ssid}", 
                            "ssid": self.current_ssid, 
                            "bssid": self.current_bssid
                        }
                    else:
                        decky.logger.error(f"Script reported failure")
                        return {
                            "success": False, 
                            "message": f"Failed to lock WiFi. Check logs for details."
                        }
                except json.JSONDecodeError as e:
                    decky.logger.error(f"Failed to parse script output as JSON: {e}")
                    return {"success": False, "message": f"Failed to parse script output: {e}", "raw_output": result.stdout}
            else:
                decky.logger.error(f"Error locking WiFi: {result.stderr}")
                return {"success": False, "message": f"Error: {result.stderr}"}
        except Exception as e:
            decky.logger.error(f"Exception while locking WiFi: {str(e)}")
            return {"success": False, "message": f"Exception: {str(e)}"}
    
    # Unlock WiFi from BSSID lock
    async def unlock_wifi(self) -> dict:
        # Check persistent state first if memory state is not locked
        ssid_to_unlock = self.current_ssid
        is_locked = self.wifi_locked

        if not is_locked and os.path.exists(self.state_file_path):
            try:
                with open(self.state_file_path, 'r') as f:
                    state = json.load(f)
                    is_locked = state.get('locked', False)
                    ssid_to_unlock = state.get('ssid')
                    decky.logger.info(f"Loaded lock state from file for unlock: locked={is_locked}, ssid={ssid_to_unlock}")
            except Exception as e:
                decky.logger.error(f"Error reading state file during unlock: {e}")
                # Proceed with potentially incorrect memory state, or fail if no ssid
                pass # is_locked and ssid_to_unlock retain values from memory

        if not is_locked:
            decky.logger.info("Unlock requested but WiFi is not locked (checked memory and file).")
            return {"success": False, "message": "WiFi not locked"}
        
        if not ssid_to_unlock:
             decky.logger.error("Unlock requested but no SSID found in state.")
             return {"success": False, "message": "Cannot unlock: Locked SSID not found."}

        try:
            decky.logger.info(f"Unlocking WiFi from BSSID lock for SSID: {ssid_to_unlock}")
            # Pass the stored SSID to the script
            result = subprocess.run([self.unlock_script_path, ssid_to_unlock], capture_output=True, text=True, env=self._get_clean_env())
            decky.logger.info(f"Unlock script exit code: {result.returncode}")
            decky.logger.info(f"Unlock script stdout: {result.stdout}")
            
            if result.stderr:
                decky.logger.error(f"Unlock script stderr: {result.stderr}")
            
            if result.returncode == 0:
                # Parse the JSON output from the script
                try:
                    output_data = json.loads(result.stdout.strip())
                    # Use the SSID passed to the script for confirmation
                    returned_ssid = output_data.get("ssid") 
                    script_success = output_data.get("success", False)
                    script_message = output_data.get("message") # Check for error message from script
                    
                    # Log raw stdout and stderr for debugging if needed
                    decky.logger.info(f"Raw script output: {result.stdout}")
                    if result.stderr:
                        decky.logger.error(f"Script stderr: {result.stderr}")

                    if script_message:
                         decky.logger.error(f"Unlock script reported message: {script_message}")
                         # Return specific error if script provided one
                         return {"success": False, "message": script_message}
                    
                    if script_success and returned_ssid == ssid_to_unlock:
                        decky.logger.info(f"WiFi unlocked for SSID: {ssid_to_unlock}")
                        self.wifi_locked = False
                        prev_ssid = self.current_ssid
                        self.current_ssid = None
                        self.current_bssid = None

                        # Delete state file
                        try:
                            if os.path.exists(self.state_file_path):
                                os.remove(self.state_file_path)
                                decky.logger.info(f"Deleted lock state file: {self.state_file_path}")
                        except Exception as e:
                            decky.logger.error(f"Error deleting state file: {e}")
                        
                        return {
                            "success": True, 
                            "message": f"WiFi unlocked from {prev_ssid or returned_ssid}"
                        }
                    elif not script_success:
                        decky.logger.error(f"Unlock script reported failure for SSID: {returned_ssid}")
                        return {
                            "success": False, 
                            "message": f"Failed to unlock WiFi. Script reported failure."
                        }
                    else: # script_success is true but SSID doesn't match?
                         decky.logger.error(f"Unlock script success mismatch: expected {ssid_to_unlock}, got {returned_ssid}")
                         return {"success": False, "message": "Unlock state mismatch. Check logs."}

                except json.JSONDecodeError as e:
                    decky.logger.error(f"Failed to parse unlock script output as JSON: {e}")
                    return {"success": False, "message": f"Failed to parse script output: {e}", "raw_output": result.stdout}
            else:
                # Handle script execution errors (e.g., script not found, permissions)
                error_message = result.stderr or f"Unlock script failed with exit code {result.returncode}"
                decky.logger.error(f"Error running unlock script: {error_message}")
                # Attempt to parse stdout for a potential JSON error message from the script itself
                try:
                    output_data = json.loads(result.stdout.strip())
                    script_message = output_data.get("message")
                    if script_message:
                        error_message = script_message
                except Exception:
                    pass # Ignore if stdout is not valid JSON
                return {"success": False, "message": f"Error: {error_message}"}
        except Exception as e:
            decky.logger.error(f"Exception while unlocking WiFi: {str(e)}")
            return {"success": False, "message": f"Exception: {str(e)}"}
    
    # Get the current WiFi lock status
    async def get_wifi_status(self) -> dict:
        return {
            "locked": self.wifi_locked,
            "ssid": self.current_ssid,
            "bssid": self.current_bssid
        }

    async def _auto_lock_on_startup(self) -> None:
        """Lock WiFi on startup if the auto_lock_on_startup setting is enabled."""
        settings = self._load_settings()
        if not settings["auto_lock_on_startup"] or self.wifi_locked:
            return
        decky.logger.info("auto_lock_on_startup is enabled — locking WiFi now.")
        try:
            lock_result = await self.lock_wifi()
            if lock_result.get("success"):
                decky.logger.info(f"Auto-lock succeeded: {lock_result.get('ssid')}")
            else:
                decky.logger.error(f"Auto-lock failed: {lock_result.get('message')}")
        except Exception as e:
            decky.logger.error(f"Exception during auto-lock on startup: {e}")

    # Get plugin settings
    async def get_settings(self) -> PluginSettings:
        return self._load_settings()

    # Set the auto-lock on startup preference
    async def set_auto_lock_on_startup(self, enabled: bool) -> dict[str, bool | str]:
        try:
            settings = self._load_settings()
            settings["auto_lock_on_startup"] = enabled
            self._save_settings(settings)
            decky.logger.info(f"auto_lock_on_startup set to {enabled}")
            return {"success": True}
        except Exception as e:
            decky.logger.error(f"Error saving auto_lock_on_startup: {e}")
            return {"success": False, "message": str(e)}
    
    # Force delete the state file and reset in-memory state
    async def force_delete_state(self) -> dict:
        decky.logger.warning("Attempting to forcefully delete WiFi lock state file and ensure unlock.")
        ssid_to_unlock = None
        state_was_locked = False
        file_existed = False
        unlock_attempted = False
        unlock_succeeded = False
        unlock_message = ""

        # 1. Try reading state file
        try:
            if os.path.exists(self.state_file_path):
                file_existed = True
                with open(self.state_file_path, 'r') as f:
                    state = json.load(f)
                    state_was_locked = state.get('locked', False)
                    if state_was_locked:
                        ssid_to_unlock = state.get('ssid')
                        decky.logger.info(f"Found locked state in file for SSID: {ssid_to_unlock}")
                    else:
                        decky.logger.info("State file existed but indicated WiFi was not locked.")
            else:
                decky.logger.info("State file did not exist.")
        except Exception as e:
            decky.logger.error(f"Error reading state file during force delete: {e}")
            # Continue with cleanup even if reading fails

        # 2. Attempt unlock if state was locked and SSID found
        if state_was_locked and ssid_to_unlock:
            unlock_attempted = True
            decky.logger.info(f"Attempting to run unlock script for SSID {ssid_to_unlock} before deleting state.")
            try:
                result = subprocess.run([self.unlock_script_path, ssid_to_unlock], capture_output=True, text=True, timeout=10, env=self._get_clean_env())
                decky.logger.info(f"Unlock script exit code during force delete: {result.returncode}")
                decky.logger.info(f"Unlock script stdout during force delete: {result.stdout}")
                if result.stderr:
                     decky.logger.error(f"Unlock script stderr during force delete: {result.stderr}")
                
                if result.returncode == 0:
                    try:
                        output_data = json.loads(result.stdout.strip())
                        if output_data.get("success", False):
                            unlock_succeeded = True
                            unlock_message = f"Successfully ran unlock command for {ssid_to_unlock}. "
                            decky.logger.info(f"Unlock script successful for {ssid_to_unlock}.")
                        else:
                           unlock_message = f"Unlock script reported failure for {ssid_to_unlock}. "
                           decky.logger.warning(f"Unlock script reported failure for {ssid_to_unlock}.")
                    except json.JSONDecodeError as e:
                         unlock_message = f"Failed to parse unlock script output for {ssid_to_unlock}. "
                         decky.logger.error(f"Failed to parse unlock script output: {e}")
                else:
                    unlock_message = f"Unlock script failed to execute for {ssid_to_unlock} (code {result.returncode}). "
                    decky.logger.error(f"Unlock script execution failed (code {result.returncode}).")
            except subprocess.TimeoutExpired:
                unlock_message = f"Unlock script timed out for {ssid_to_unlock}. "
                decky.logger.error("Unlock script timed out during force delete.")
            except Exception as e:
                unlock_message = f"Exception running unlock script for {ssid_to_unlock}: {e}. "
                decky.logger.error(f"Exception running unlock script: {str(e)}")
        elif state_was_locked and not ssid_to_unlock:
             decky.logger.warning("State file indicated lock but SSID was missing. Cannot attempt unlock.")
             unlock_message = "State locked but SSID missing, unlock not attempted. "

        # 3. Delete state file
        delete_succeeded = False
        delete_message = ""
        try:
            if file_existed:
                os.remove(self.state_file_path)
                delete_succeeded = True
                delete_message = "Successfully deleted state file. "
                decky.logger.info(f"Successfully deleted state file: {self.state_file_path}")
            else:
                delete_succeeded = True # Consider success if file didn't exist
                delete_message = "State file did not exist. "
        except Exception as e:
            delete_message = f"Error deleting state file: {str(e)}. "
            decky.logger.error(f"Error deleting state file: {str(e)}")

        # 4. Reset in-memory state
        self.wifi_locked = False
        self.current_ssid = None
        self.current_bssid = None
        decky.logger.info("In-memory lock state reset.")
        reset_message = "In-memory state reset."
        
        # 5. Construct final message and return status
        final_message = unlock_message + delete_message + reset_message
        # Overall success depends on state file deletion and memory reset
        overall_success = delete_succeeded 

        return {"success": overall_success, "message": final_message.strip()}
    
    # Asyncio-compatible long-running code, executed in a task when the plugin is loaded
    async def _main(self):
        self.loop = asyncio.get_event_loop()
        # Ensure runtime directory exists
        os.makedirs(decky.DECKY_PLUGIN_RUNTIME_DIR, exist_ok=True)

        # Load persistent state
        try:
            if os.path.exists(self.state_file_path):
                with open(self.state_file_path, 'r') as f:
                    state = json.load(f)
                    self.wifi_locked = state.get('locked', False)
                    self.current_ssid = state.get('ssid')
                    self.current_bssid = state.get('bssid')
                    if self.wifi_locked:
                        decky.logger.info(f"Loaded previous lock state: SSID={self.current_ssid}, BSSID={self.current_bssid}")
                    else:
                        decky.logger.info("Loaded previous state: WiFi was not locked.")
            else:
                 decky.logger.info("No previous lock state file found.")
                 self.wifi_locked = False
                 self.current_ssid = None
                 self.current_bssid = None
        except Exception as e:
            decky.logger.error(f"Error loading state file: {e}")
            # Reset state if loading fails
            self.wifi_locked = False
            self.current_ssid = None
            self.current_bssid = None

        await self._auto_lock_on_startup()

        decky.logger.info("WiFi Locker plugin initialized")

    # Function called first during the unload process, utilize this to handle your plugin being stopped
    async def _unload(self):
        # Ensure WiFi is unlocked when plugin is unloaded
        if self.wifi_locked or os.path.exists(self.state_file_path):
            decky.logger.info("Attempting to unlock WiFi during unload...")
            try:
                # Call the modified unlock_wifi which handles state loading/clearing
                unlock_result = await self.unlock_wifi()
                if unlock_result.get("success"):
                    decky.logger.info("Successfully unlocked WiFi during unload.")
                else:
                    decky.logger.error(f"Failed to unlock WiFi during unload: {unlock_result.get('message')}")
            except Exception as e:
                decky.logger.error(f"Error unlocking WiFi during unload: {str(e)}")
        decky.logger.info("WiFi Locker plugin unloaded")

    # Function called after `_unload` during uninstall, utilize this to clean up processes
    async def _uninstall(self):
        decky.logger.info("WiFi Locker plugin uninstalled")

    # Migrations that should be performed before entering `_main()`.
    async def _migration(self):
        decky.logger.info("Migrating WiFi Locker plugin")
        # Migrate logs
        decky.migrate_logs(os.path.join(decky.DECKY_USER_HOME,
                                        ".config", "decky-wifi-locker", "wifi-locker.log"))
        # Migrate settings
        decky.migrate_settings(
            os.path.join(decky.DECKY_HOME, "settings", "wifi-locker.json"),
            os.path.join(decky.DECKY_USER_HOME, ".config", "decky-wifi-locker"))
        # Migrate runtime data
        decky.migrate_runtime(
            os.path.join(decky.DECKY_HOME, "wifi-locker"),
            os.path.join(decky.DECKY_USER_HOME, ".local", "share", "decky-wifi-locker"))
        # If defaults folder exists, this should be a manual install, then we need to copy the scripts to the runtime folder

        if os.path.exists(os.path.join(decky.DECKY_PLUGIN_DIR, "defaults")):
            decky.logger.info("Copying scripts to runtime folder for manual install.")
            os.makedirs(decky.DECKY_PLUGIN_RUNTIME_DIR, exist_ok=True)
            shutil.copy(os.path.join(decky.DECKY_PLUGIN_DIR, "defaults", "assets", "lock_wifi.sh"), self.lock_script_path)
            shutil.copy(os.path.join(decky.DECKY_PLUGIN_DIR, "defaults", "assets", "unlock_wifi.sh"), self.unlock_script_path)
        os.chmod(self.lock_script_path, 0o755)
        os.chmod(self.unlock_script_path, 0o755)
