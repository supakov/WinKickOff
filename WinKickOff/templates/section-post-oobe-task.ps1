# ============================================================================
# POST-OOBE TASK (waits for OOBE to finish, runs Post-OOBE.ps1, then removes itself)
# ============================================================================
# schtasks.exe with a task XML instead of Register-ScheduledTask: the CIM/WMI layer the cmdlet needs is not reliable
# during specialize, and the XML lets the task run on battery (schtasks /SC defaults to AC power only).
$taskXml = @'
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Unattend post-OOBE cleanup (self-removing)</Description></RegistrationInfo>
  <Triggers><BootTrigger><Enabled>true</Enabled></BootTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT6H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\ProgramData\Unattend\Scripts\Post-OOBE.ps1</Arguments>
    </Exec>
  </Actions>
</Task>
'@
$taskFile = 'C:\ProgramData\Unattend\Scripts\Post-OOBE.task.xml'
try { $taskXml | Out-File -FilePath $taskFile -Encoding Unicode -Force } catch { Write-Log "task xml: $($_.Exception.Message)" 'ERROR' }
Invoke-Exe 'schtasks.exe' @('/Create','/F','/TN','Unattend-PostOOBE','/XML',$taskFile)
