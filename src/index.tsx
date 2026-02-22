import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  staticClasses,
  Field,
  ToggleField
} from "@decky/ui";
import {
  callable,
  definePlugin,
  toaster,
} from "@decky/api"
import { useState, useEffect } from "react";
import { FaWifi, FaLock, FaLockOpen, FaTrash } from "react-icons/fa";

// Define callable functions for WiFi locking operations
const lockWifi = callable<[], any>("lock_wifi");
const unlockWifi = callable<[], any>("unlock_wifi");
const getWifiStatus = callable<[], any>("get_wifi_status");
const forceDeleteState = callable<[], any>("force_delete_state");
const getSettings = callable<[], any>("get_settings");
const setAutoLockOnStartup = callable<[{ enabled: boolean }], any>("set_auto_lock_on_startup");

function Content() {
  const [wifiStatus, setWifiStatus] = useState<{
    locked: boolean;
    ssid: string | null;
    bssid: string | null;
  }>({ locked: false, ssid: null, bssid: null });
  const [isLocking, setIsLocking] = useState<boolean>(false);
  const [isUnlocking, setIsUnlocking] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [autoLockOnStartup, setAutoLockOnStartupState] = useState<boolean>(false);

  // Function to refresh the WiFi status
  const refreshWifiStatus = async () => {
    try {
      const status = await getWifiStatus();
      setWifiStatus(status);
    } catch (error) {
      console.error("Error getting WiFi status:", error);
      toaster.toast({
        title: "Error",
        body: "Failed to get WiFi status",
        icon: <FaWifi />,
        critical: true
      });
    }
  };

  // Load WiFi status and settings on component mount
  useEffect(() => {
    refreshWifiStatus();
    getSettings().then((s: any) => {
      setAutoLockOnStartupState(s?.auto_lock_on_startup ?? false);
    }).catch((err: any) => console.error("Error loading settings:", err));
  }, []);

  // Handle WiFi locking
  const handleLockWifi = async () => {
    setIsLocking(true);
    try {
      const result = await lockWifi();
      if (result.success) {
        toaster.toast({
          title: "WiFi Locked",
          body: `Locked to ${result.ssid}`,
          icon: <FaLock />
        });
        await refreshWifiStatus();
      } else {
        console.error("Lock error details:", result);
        
        toaster.toast({
          title: "Error",
          body: result.message,
          icon: <FaWifi />,
          critical: true
        });
      }
    } catch (error) {
      console.error("Error locking WiFi:", error);
      toaster.toast({
        title: "Error",
        body: "Failed to lock WiFi",
        icon: <FaWifi />,
        critical: true
      });
    } finally {
      setIsLocking(false);
    }
  };

  // Handle WiFi unlocking
  const handleUnlockWifi = async () => {
    setIsUnlocking(true);
    try {
      const result = await unlockWifi();
      if (result.success) {
        toaster.toast({
          title: "WiFi Unlocked",
          body: result.message,
          icon: <FaLockOpen />
        });
        await refreshWifiStatus();
      } else {
        console.error("Unlock error details:", result);
        
        toaster.toast({
          title: "Error",
          body: result.message,
          icon: <FaWifi />,
          critical: true
        });
      }
    } catch (error) {
      console.error("Error unlocking WiFi:", error);
      toaster.toast({
        title: "Error",
        body: "Failed to unlock WiFi",
        icon: <FaWifi />,
        critical: true
      });
    } finally {
      setIsUnlocking(false);
    }
  };

  // Handle Force Delete State
  const handleForceDeleteState = async () => {
    setIsResetting(true);
    try {
      const result = await forceDeleteState();
      if (result.success) {
        toaster.toast({
          title: "State Reset",
          body: result.message,
          icon: <FaTrash />
        });
        // Refresh status after deleting state
        await refreshWifiStatus(); 
      } else {
        toaster.toast({
          title: "Error",
          body: result.message,
          icon: <FaWifi />,
          critical: true
        });
      }
    } catch (error) {
      console.error("Error forcing state deletion:", error);
      toaster.toast({
        title: "Error",
        body: "Failed to reset lock state",
        icon: <FaWifi />,
        critical: true
      });
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <>
      <PanelSection title="About WiFi Locker">
        <PanelSectionRow>
          <Field
            label="What This Does"
            description="Locks your WiFi to the current access point, preventing background scanning."
            icon={<FaWifi />}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field
            label="Benefits"
            description="Reduces latency spikes during gaming, improves connection stability, and may help save battery life."
            icon={<FaLock />}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field
            label="When To Use"
            description="Use when you're in a fixed location with a good WiFi signal. Remember to unlock when you move to a different location."
            icon={<FaLockOpen />}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="WiFi Locker">
        {wifiStatus.locked ? (
        <>
          <PanelSectionRow>
            <Field
              label="Status"
              description={`Locked to ${wifiStatus.ssid || 'Unknown'}`}
              icon={<FaLock />}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <Field
              label="BSSID"
              description={wifiStatus.bssid || 'Unknown'}
              icon={<FaWifi />}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={handleUnlockWifi}
              disabled={isUnlocking || isLocking || isResetting}
            >
              {isUnlocking ? "Unlocking..." : "Unlock WiFi"}
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : (
        <>
          <PanelSectionRow>
            <Field
              label="Status"
              description="WiFi is not locked"
              icon={<FaLockOpen />}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={handleLockWifi}
              disabled={isLocking || isUnlocking || isResetting}
            >
              {isLocking ? "Locking..." : "Lock WiFi to Current AP"}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      <PanelSectionRow>
        <ToggleField
          label="Auto-lock on startup"
          description="Automatically lock WiFi when the plugin loads"
          checked={autoLockOnStartup}
          disabled={isLocking || isUnlocking || isResetting}
          onChange={async (value: boolean) => {
            setAutoLockOnStartupState(value);
            try {
              await setAutoLockOnStartup({ enabled: value });
            } catch (err) {
              console.error("Error saving auto-lock setting:", err);
              setAutoLockOnStartupState(!value);
            }
          }}
        />
      </PanelSectionRow>
    </PanelSection>

    <PanelSection title="Troubleshooting">
      <PanelSectionRow>
        <p style={{ fontSize: '0.95em', fontWeight: 'bold', color: '#ffcc00', textAlign: 'center', marginBottom: '10px' }}>
          Use this ONLY if the lock status seems incorrect or stuck.
        </p>
        <ButtonItem
          layout="below"
          onClick={handleForceDeleteState}
          disabled={isResetting || isLocking || isUnlocking}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '5px' }}>
            <FaTrash /> 
            {isResetting ? "Resetting..." : "Force Reset Lock State"}
          </div>
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
    </>
  );
};

export default definePlugin(() => {
  console.log("WiFi Locker plugin initializing")

  return {
    // The name shown in various decky menus
    name: "WiFi Locker",
    // The element displayed at the top of your plugin's menu
    titleView: <div className={staticClasses.Title}>WiFi Locker</div>,
    // The content of your plugin's menu
    content: <Content />,
    // The icon displayed in the plugin list
    icon: <FaWifi />,
    // The function triggered when your plugin unloads
    onDismount() {
      console.log("WiFi Locker unloading")
    },
  };
});
