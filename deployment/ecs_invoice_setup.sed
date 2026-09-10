[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=D:\python\invoice\deployment\dist\ECS_Invoice_Tool_Setup.exe
FriendlyName=ECS Invoice Tool Setup
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=install.cmd
UserQuietInstCmd=install.cmd
SourceFiles=SourceFiles

[SourceFiles]
SourceFiles0=D:\python\invoice\deployment\installer_staging\

[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=

[Strings]
FILE0="install.cmd"
FILE1="install.ps1"
FILE2="payload.zip"
