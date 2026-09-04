@echo off
chcp 65001 >nul
REM ============================================================
REM  创可贴制作-内容搜索打开工具 - Windows 一键打包脚本
REM  用法：在 Windows 电脑上双击本文件（需已安装 Python 3.10+）
REM  产物：dist\创可贴制作-内容搜索打开工具.exe（单文件，双击即可运行）
REM ============================================================
setlocal

echo [1/3] 安装打包依赖...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :err

echo [2/3] 开始打包...
python -m PyInstaller --noconfirm --clean ^
  --onefile --windowed ^
  --name "创可贴制作-内容搜索打开工具" ^
  --icon "app.ico" ^
  --add-data "app.ico;." ^
  "main.py"
if errorlevel 1 goto :err

echo [3/3] 完成！
echo.
echo 生成文件：dist\创可贴制作-内容搜索打开工具.exe
echo 可以把它重命名为“内容搜索并打开工具.exe”后拷贝到任意 Windows 电脑使用。
echo （如需安装程序，请安装 Inno Setup 后运行 build_installer.iss）
pause
exit /b 0

:err
echo.
echo 打包失败，请检查上方错误信息。
pause
exit /b 1
