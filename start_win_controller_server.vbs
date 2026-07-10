' Clickable, windowless launcher for the Mac/Win Controller server (Windows).
' Double-click to start the tray app with NO console window. Paths are resolved
' relative to this file, so the whole repo folder can be moved/renamed freely.
' This is the Windows analog of the macOS Automator "Mac Controller.app".

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw   = fso.BuildPath(scriptDir, "venv\Scripts\pythonw.exe")  ' windowless Python
app       = fso.BuildPath(scriptDir, "app.py")

If Not fso.FileExists(pythonw) Then
    MsgBox "venv not found at:" & vbCrLf & pythonw & vbCrLf & vbCrLf & _
           "Run setup.ps1 first.", vbCritical, "Mac Controller"
    WScript.Quit 1
End If

sh.CurrentDirectory = scriptDir
' Window style 0 = hidden; False = do not wait for it to exit (runs in background).
sh.Run """" & pythonw & """ """ & app & """", 0, False
