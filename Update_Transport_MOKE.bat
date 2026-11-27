@echo off
rem ===========================================================================
rem  Update_Transport_MOKE.bat
rem
rem  Puts the newest Transport_MOKE.exe into the folder this file is in.
rem  Double-click it.  It needs the internet and nothing else: it uses
rem  curl, certutil and tasklist, which are parts of Windows 10 and 11.
rem
rem  What it does:
rem    1. reads the program's version from GitHub (branch Transport-MOKE of
rem       nbb2026/Transport-all) and the SHA-256 of that version's exe;
rem    2. if the Transport_MOKE.exe here already has that SHA-256: nothing;
rem    3. if Transport_MOKE.exe is running: nothing (a measurement may be
rem       running; close the program and run this again);
rem    4. otherwise downloads the exe, checks its SHA-256, puts it in
rem       place and deletes the old one (also a Transport_MOKE_previous.exe
rem       that the first version of this file left behind).
rem  A download that fails or does not match its SHA-256 changes nothing:
rem  the old exe stays.
rem
rem  Options (type them after the file name, or edit the line below):
rem    quiet   do not wait for a key at the end
rem    start   start Transport_MOKE.exe afterwards
rem
rem  Exit code: 0 the newest exe is here; 1 not updated; 2 it is running.
rem ===========================================================================
setlocal EnableExtensions DisableDelayedExpansion

rem 1 = always start the program afterwards (use this file as the shortcut)
set "START_AFTER=0"

set "NAME=Transport_MOKE"
set "VERSION_URL=https://raw.githubusercontent.com/nbb2026/Transport-all/Transport-MOKE/pyproject.toml"
set "RELEASE_URL=https://github.com/nbb2026/Transport-all/releases/download"
set "TAG_PREFIX=moke-v"

set "EXE=%NAME%.exe"
rem The old exe's name while the new one is put in place; deleted afterwards.
set "PREVIOUS=%NAME%_previous.exe"
set "HAD_OLD=0"
set "INFO=%NAME%_BUILD_INFO.txt"
set "RESULT=1"
set "QUIET=0"
set "VERSION="
set "NEW_HASH="
set "OLD_HASH="
set "HASH="

rem This file's folder, before the options are read: "shift" would move %%0 too.
pushd "%~dp0"
if errorlevel 1 goto no_folder

:arguments
if "%~1"=="" goto arguments_done
if /i "%~1"=="quiet" set "QUIET=1"
if /i "%~1"=="start" set "START_AFTER=1"
shift /1
goto arguments
:arguments_done

echo %NAME% update
rem (through a for variable: a folder name with an ampersand must not be run as a command)
for %%I in (.) do echo Folder: %%~fI
echo.

where curl.exe >nul 2>nul
if errorlevel 1 goto no_curl

rem --- 1. the version and its SHA-256 -----------------------------------------
curl.exe -fsSL --connect-timeout 15 --max-time 60 -o "_update_version.tmp" "%VERSION_URL%"
if errorlevel 1 goto no_internet
for /f "tokens=2 delims== " %%V in ('findstr /b /c:"version" "_update_version.tmp"') do if not defined VERSION set "VERSION=%%~V"
if not defined VERSION goto bad_version
echo %VERSION%| findstr /r /x "[0-9][0-9.]*" >nul
if errorlevel 1 goto bad_version
set "BASE=%RELEASE_URL%/%TAG_PREFIX%%VERSION%"

curl.exe -fsSL --connect-timeout 15 --max-time 60 -o "_update_sha256.tmp" "%BASE%/%EXE%.sha256"
if errorlevel 1 goto no_release
for /f "usebackq tokens=1" %%H in ("_update_sha256.tmp") do if not defined NEW_HASH set "NEW_HASH=%%H"
if not defined NEW_HASH goto bad_hash_file
echo %NEW_HASH%| findstr /r /x /i "[0-9a-f]*" >nul
if errorlevel 1 goto bad_hash_file
if "%NEW_HASH:~63,1%"=="" goto bad_hash_file
if not "%NEW_HASH:~64,1%"=="" goto bad_hash_file

rem --- 2. the exe here ---------------------------------------------------------
if not exist "%EXE%" goto download
set "HAD_OLD=1"
call :hash "%EXE%"
set "OLD_HASH=%HASH%"
if /i "%OLD_HASH%"=="%NEW_HASH%" goto already_newest

rem --- 3. never under a running program ----------------------------------------
tasklist /FI "IMAGENAME eq %EXE%" /NH 2>nul | find /I "%EXE%" >nul
if not errorlevel 1 goto running

rem --- 4. download, check, replace ---------------------------------------------
:download
echo Downloading %NAME% %VERSION% ...
curl.exe -fL --connect-timeout 15 --retry 2 -# -o "%EXE%.download" "%BASE%/%EXE%"
if errorlevel 1 goto download_failed
call :hash "%EXE%.download"
if /i not "%HASH%"=="%NEW_HASH%" goto download_mismatch
if not exist "%EXE%" goto put_new
move /y "%EXE%" "%PREVIOUS%" >nul
if errorlevel 1 goto old_in_use
:put_new
move /y "%EXE%.download" "%EXE%" >nul
if errorlevel 1 goto put_failed
if exist "%PREVIOUS%" del /f /q "%PREVIOUS%" >nul 2>nul
curl.exe -fsSL --connect-timeout 15 --max-time 60 -o "%INFO%" "%BASE%/BUILD_INFO.txt" 2>nul
echo.
echo UPDATED: %EXE% is now the newest (version %VERSION%).
if exist "%INFO%" findstr /b /c:"Commit:" /c:"Built:" "%INFO%"
if exist "%PREVIOUS%" echo The old one could not be deleted: it is still here as %PREVIOUS%.
if not exist "%PREVIOUS%" if "%HAD_OLD%"=="1" echo The old one is deleted.
set "RESULT=0"
goto finish

:already_newest
echo UP TO DATE: %EXE% is already the newest (version %VERSION%).
set "RESULT=0"
if not exist "%PREVIOUS%" goto finish
del /f /q "%PREVIOUS%" >nul 2>nul
if not exist "%PREVIOUS%" echo The old %PREVIOUS% left by an earlier update is deleted.
goto finish

:running
echo NOT UPDATED: %EXE% is running, and a newer one is on GitHub.
echo Close the program (after the measurement) and run this again.
set "RESULT=2"
goto finish

:no_folder
echo NOT UPDATED: this file's folder cannot be opened.
goto finish_no_folder
:no_curl
echo NOT UPDATED: curl.exe was not found (it comes with Windows 10 and 11).
goto finish
:no_internet
echo NOT UPDATED: GitHub could not be reached. Is this computer online?
goto finish
:bad_version
echo NOT UPDATED: the version on GitHub could not be read.
goto finish
:no_release
echo NOT UPDATED: the files of version %VERSION% are not on GitHub yet
echo (a new build may be running; try again in ten minutes).
goto finish
:bad_hash_file
echo NOT UPDATED: the SHA-256 file on GitHub could not be read.
goto finish
:download_failed
echo NOT UPDATED: the download failed. The exe here is unchanged.
goto finish
:download_mismatch
echo NOT UPDATED: the downloaded file does not match its SHA-256
echo (a new build may be uploading; try again in a minute). The exe here is unchanged.
goto finish
:old_in_use
echo NOT UPDATED: the %EXE% here could not be moved (is it open?). It is unchanged.
goto finish
:put_failed
echo NOT UPDATED: the new exe could not be put in place.
if exist "%EXE%" goto finish
if exist "%PREVIOUS%" move /y "%PREVIOUS%" "%EXE%" >nul
goto finish

:finish
if exist "%EXE%.download" del /q "%EXE%.download" >nul 2>nul
if exist "_update_version.tmp" del /q "_update_version.tmp" >nul 2>nul
if exist "_update_sha256.tmp" del /q "_update_sha256.tmp" >nul 2>nul
if not "%START_AFTER%"=="1" goto finish_no_start
if not exist "%EXE%" goto finish_no_start
tasklist /FI "IMAGENAME eq %EXE%" /NH 2>nul | find /I "%EXE%" >nul
if not errorlevel 1 goto finish_no_start
echo Starting %EXE% ...
start "" "%EXE%"
:finish_no_start
popd
:finish_no_folder
echo.
if "%QUIET%"=="0" pause
exit /b %RESULT%

rem The SHA-256 of file %%1 in HASH (empty when it cannot be read).
:hash
set "HASH="
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%~1" SHA256 2^>nul') do if not defined HASH set "HASH=%%H"
if defined HASH set "HASH=%HASH: =%"
exit /b 0
