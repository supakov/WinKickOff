# ============================================================================
# DATA FORMS OF THE PROFILE: edition, time zone, computer name, languages, local accounts (read only)
# ============================================================================
# "Read the settings of this PC" puts these values into the forms of the new profile. Passwords and product keys are
# never read.
$System = [ordered]@{ computer_name = $env:COMPUTERNAME }
try {
    $cv = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction Stop
    $System.edition_id = [string]$cv.EditionID
    $System.build = [string]$cv.CurrentBuild
    $System.display_version = [string]$cv.DisplayVersion
} catch { }
try { $System.time_zone = [string](Get-TimeZone).Id } catch { }
try { $System.ui_language = [System.Globalization.CultureInfo]::InstalledUICulture.Name } catch { }
try { $System.system_locale = [string](Get-WinSystemLocale).Name } catch { }
try { $System.user_locale = [string](Get-Culture).Name } catch { }
try {
    $System.input = @(Get-WinUserLanguageList | ForEach-Object { [pscustomobject]@{ tag = [string]$_.LanguageTag; tips = @($_.InputMethodTips | ForEach-Object { [string]$_ }) } })
} catch { }
try {
    # group membership through ADSI: Get-LocalGroupMember fails on a group that holds an orphaned or cloud SID
    $members = @{}
    foreach ($group in 'S-1-5-32-544', 'S-1-5-32-545') {
        $name = ([System.Security.Principal.SecurityIdentifier]$group).Translate([System.Security.Principal.NTAccount]).Value.Split('\')[-1]
        $adsi = [ADSI]('WinNT://{0}/{1},group' -f $env:COMPUTERNAME, $name)
        $members[$group] = @($adsi.Invoke('Members') | ForEach-Object { (New-Object System.Security.Principal.SecurityIdentifier($_.GetType().InvokeMember('objectSid', 'GetProperty', $null, $_, $null), 0)).Value })
    }
    $System.accounts = @(Get-LocalUser -ErrorAction Stop | Where-Object { $_.Enabled -and $_.SID.Value -notmatch '-(500|501|503|504)$' } | ForEach-Object {
        $sid = $_.SID.Value
        $group = if ($members['S-1-5-32-544'] -contains $sid) { 'Administrators' } elseif ($members['S-1-5-32-545'] -contains $sid) { 'Users' } else { '' }
        [pscustomobject]@{ name = [string]$_.Name; full_name = [string]$_.FullName; description = [string]$_.Description; group = $group }
    })
} catch { $System.accounts_error = $_.Exception.Message }
