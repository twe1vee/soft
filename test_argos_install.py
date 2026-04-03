import argostranslate.package
import argostranslate.translate

print("Fetching available Argos packages...")
available_packages = argostranslate.package.get_available_packages()

pt_ru = None
pt_en = None
en_ru = None

for pkg in available_packages:
    if pkg.from_code == "pt" and pkg.to_code == "ru":
        pt_ru = pkg
    elif pkg.from_code == "pt" and pkg.to_code == "en":
        pt_en = pkg
    elif pkg.from_code == "en" and pkg.to_code == "ru":
        en_ru = pkg

if pt_ru:
    print("Installing direct model: pt -> ru")
    download_path = pt_ru.download()
    argostranslate.package.install_from_path(download_path)
    print("Installed pt -> ru")
else:
    print("Direct pt -> ru not found, trying pivot pt -> en -> ru")

    if not pt_en:
        raise RuntimeError("Model pt -> en not found")
    if not en_ru:
        raise RuntimeError("Model en -> ru not found")

    download_path = pt_en.download()
    argostranslate.package.install_from_path(download_path)
    print("Installed pt -> en")

    download_path = en_ru.download()
    argostranslate.package.install_from_path(download_path)
    print("Installed en -> ru")

print("Installed languages:")
langs = argostranslate.translate.get_installed_languages()
for lang in langs:
    print("-", lang.code)

print("Done")