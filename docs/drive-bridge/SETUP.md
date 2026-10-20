# Drive bridge: setup (about 5 minutes, once)

Campaign OS can only read Drive. The bridge is a small Google Apps Script, run as you, that lets the
app do three things in the brand folders: **move a file** (Mark posted), **change a caption** and
**create a caption**. It cannot delete anything, change sharing, or touch files outside the Stick and
Swing Shack folders.

## 1. Make the script
1. Go to https://script.google.com and sign in as the Google account that owns the brand folders (christellew@fivefriday.com).
2. Click **New project**. Name it `Campaign OS Drive bridge`.
3. Delete the starting code and paste in the whole of `drive-bridge.gs` from this folder. Save.

## 2. Give it a secret
1. In the script, click the gear (**Project settings**), then **Script properties**, then **Add script property**.
2. Name: `BRIDGE_TOKEN`. Value: a long random string you make up yourself (40 or more letters and numbers; a password manager can generate one). Do not reuse a password, and do not paste it into chat. It goes in two places only: here and in Railway.
3. Save the properties.

## 3. Deploy it
1. Click **Deploy**, then **New deployment**. Choose the type **Web app**.
2. **Execute as:** Me. **Who has access:** Anyone. (The secret token is what protects it.)
3. Click **Deploy**. Google asks you to allow Drive access: click through and allow it (you may need **Advanced**, then **Go to Campaign OS Drive bridge**).
4. Copy the **Web app URL** (it ends in `/exec`).

## 4. Tell Campaign OS
In Railway, project `heartfelt-wholeness`, service `swing-shack-dashboard`, add two variables:
- `DRIVE_BRIDGE_URL` = the Web app URL
- `DRIVE_BRIDGE_TOKEN` = the same secret you put in the script

Railway restarts the app. Then Today > Photos > Video shows working **Mark posted** and **Edit caption** buttons.

## Changing it later
If you edit the script, use **Deploy > Manage deployments > Edit > New version**, so the URL stays the same.
To turn the bridge off, delete the two Railway variables. To revoke it fully, delete the deployment in Apps Script.
