import os

filepath = 'app.py'
with open(filepath, 'r') as f:
    lines = f.readlines()

main_idx = -1
for i, line in enumerate(lines):
    if "if __name__ == '__main__':" in line:
        main_idx = i
        break

if main_idx != -1:
    before_main = lines[:main_idx]
    after_main = lines[main_idx:]

    # Remove app.run block and put it at the very end
    run_block = []
    other_after = []
    in_run = False
    for line in after_main:
        if "if __name__ == '__main__':" in line:
            in_run = True
            run_block.append(line)
        elif in_run and (line.startswith(" ") or line.strip() == ""):
            run_block.append(line)
        else:
            in_run = False
            other_after.append(line)

    new_content = "".join(before_main) + "".join(other_after) + "\n" + "".join(run_block)
    with open(filepath, 'w') as f:
        f.write(new_content)
    print("app.py structural fix applied.")
