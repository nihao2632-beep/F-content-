# 内容搜索并打开工具

一个简单的小工具：**输入一段文字 → 选择一个文件夹 → 自动找出该文件夹下所有“内容包含这段文字”的文件 → 用系统默认程序全部打开**。可打包为 Windows 单文件 `.exe`（无需安装 Python 即可运行），也可再生成安装程序。

> 使用场景示例：把「1.现教处…申请动议.docx」「2.现教处…申请动议.docx」这类 Word 文档放在一个文件夹里，
> 输入“党委会”或“6万元”，工具就能找出**内容里**包含这些文字的所有文件并把它们一起打开。

---

## 一、主要功能

- 搜索范围：**所选文件夹**（可勾选包含/不包含子文件夹）
- 搜索对象：**文件内容**（不是文件名；可选“文件名包含也算命中”）
- 支持的文件格式
  - 文本类：txt / md / csv / log / json / xml / html / 源码等（自动识别 UTF-8、GBK、UTF-16、Big5 编码）
  - Word：`.docx`（含页眉页脚）；旧版 `.doc` 走二进制扫描
  - Excel：`.xlsx`；PowerPoint：`.pptx`；OpenDocument：`.odt/.ods/.odp`
  - PDF：`.pdf`（安装 `pypdf` 后按文字提取，未安装时退回二进制扫描）
  - 其它任意文件：直接对文件字节流查找（UTF-8 / GB18030 / UTF-16LE 三种编码）
- 结果：列表显示全部命中文件，可**一键全部打开**，也可只打开选中的几个、复制路径
- 细节：可限制文件类型、单个文件大小上限；记忆上次使用的文件夹与关键词

---

## 二、项目结构

| 文件 | 说明 |
| --- | --- |
| `main.py` | 图形界面主程序（Python 标准库 tkinter 编写，无第三方运行库） |
| `searcher.py` | 内容搜索核心引擎（纯标准库） |
| `app.ico` / `app_icon.png` | 程序图标 |
| `requirements.txt` | 打包依赖（pyinstaller；pypdf 可选） |
| `build_exe.bat` | **Windows 一键打包脚本**（生成单文件 exe） |
| `build_installer.iss` | 可选：Inno Setup 安装程序脚本（生成真正的“安装包”） |
| `.github/workflows/build-windows-exe.yml` | 可选：推送到 GitHub 后自动构建 exe |

---

## 三、在 Windows 电脑上打包成 exe（推荐，最简单）

在一台 **Windows 10/11** 电脑上：

1. 安装 Python：到 <https://www.python.org/downloads/> 下载安装，**安装时勾选 “Add Python to PATH”**（3.10 及以上即可）。
2. 把本项目文件夹拷贝到该电脑，双击 **`build_exe.bat`**。
3. 等待脚本执行完毕，产物在 **`dist\ContentSearchOpener.exe`**。
4. 该 exe 是“单文件、免安装”程序：拷贝到任意 Windows 电脑双击即可使用；也可自行改名为 `内容搜索并打开工具.exe`。

> 需要“安装程序”（带桌面快捷方式、可卸载）时：再安装 [Inno Setup 6](https://jrsoftware.org/isdl.php)，
> 双击打开 `build_installer.iss` → 菜单 Build → Compile，产物在 `Output\ContentSearchOpener_Setup.exe`。

---

## 四、自动构建（没有 Windows 电脑也能拿到 exe）

把本项目推到 GitHub 后：

1. 仓库页面 → **Actions** → 左侧 **Build Windows EXE** → **Run workflow**；
2. 跑完后打开该次运行页面底部的 **Artifacts**，下载 `ContentSearchOpener-exe`（单文件 exe）或 `ContentSearchOpener-installer`（安装程序）。

---

## 五、为什么当前这台 Mac 上不能直接“生成 Windows exe”？

`PyInstaller` 不支持跨平台交叉编译：在 macOS 上只能生成 Mac 程序，**Windows 的 .exe 必须在 Windows（或 Windows 虚拟/云构建机）上打包**。
因此本目录已把源码、图标、`build_exe.bat`、Inno Setup 脚本、GitHub Actions 自动构建全部准备好——在任意 Windows 电脑上双击 `build_exe.bat`，或推送到 GitHub 让 Actions 构建，即可得到可安装使用的 exe。

本机可用下面的命令先**验证搜索功能**（无需图形界面）：

```bash
python3 main.py --cli --dir "要搜索的文件夹" --text "要查找的内容"
```

---

## 六、开发自测记录

用两份示例 Word 文档验证过（放在 `/tmp/search_test`）：

| 搜索内容 | 预期命中 | 实际 |
| --- | --- | --- |
| 党委会 | 2 个 docx | ✅ 2 |
| 安装网络 | 仅“5个新办公室安装网络申请动议” | ✅ 1 |
| 打印（复）机维修 | 仅“打印（复）机维修申请动议” | ✅ 1 |
| 6万元 | 仅“打印（复）机维修申请动议” | ✅ 1 |
| 现代教育技术处 | 2 个 docx + 1 个 txt | ✅ 3 |
| abc（忽略大小写） | 文本文件 | ✅ 命中 |

> 注意：内容搜索按**正文文字**匹配。例如文件名里的“现教处”在正文中写作“现代教育技术处”，
> 搜索“现教处”不会命中正文——这正是“按内容搜索”与“按文件名搜索”的区别（可勾选“文件名包含也算命中”）。
