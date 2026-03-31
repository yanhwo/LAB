import os
import shutil
from pathlib import Path


def delete_all_except(root_dir, keep_filename):
    """
    遍历文件夹的所有子文件夹，删除除指定文件外的所有文件和文件夹

    参数:
        root_dir: 根目录路径
        keep_filename: 要保留的文件名
    """
    root_path = Path(root_dir)

    if not root_path.exists():
        print(f"错误: 目录 '{root_dir}' 不存在")
        return

    # 遍历所有子目录
    for dirpath, dirnames, filenames in os.walk(root_path, topdown=False):
        current_dir = Path(dirpath)

        # 跳过根目录本身
        if current_dir == root_path:
            continue

        print(f"\n处理目录: {current_dir}")

        # 删除所有文件（除了要保留的）
        for filename in filenames:
            if filename != keep_filename:
                file_path = current_dir / filename
                try:
                    file_path.unlink()
                    print(f"  已删除文件: {filename}")
                except Exception as e:
                    print(f"  删除文件失败 {filename}: {e}")
            else:
                print(f"  保留文件: {filename}")

        # 删除所有子文件夹
        for dirname in dirnames:
            dir_path = current_dir / dirname
            try:
                shutil.rmtree(dir_path)
                print(f"  已删除文件夹: {dirname}")
            except Exception as e:
                print(f"  删除文件夹失败 {dirname}: {e}")

def gen_json(path):
    res = []
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        if len(filenames) == 1:
            res.append(
                {
                    'plan_id': os.path.basename(dirpath),
                    'tuning_bin_path': os.path.join(dirpath, filenames[0])
                }
            )
    import json
    with open(r'C:\workspace\share_all\yanhao\Sim\Contrast\plan_sim.json', 'r', encoding='utf-8') as f:
        task_data = json.load(f)

    task_data['plan'] = res

    with open(r'C:\workspace\share_all\yanhao\Sim\Contrast\plan_sim.json', 'w', encoding='utf-8') as f:
        json.dump(task_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # # 使用示例
    # root_directory = r"C:\workspace\share_all\yanhao\Sim\Contrast"  # 修改为你的目标文件夹
    # keep_file = "com.qti.tuned.qtech_imx858.canoe.bin"  # 修改为你要保留的文件名
    #
    # # 安全确认
    # print(f"将要处理目录: {root_directory}")
    # print(f"保留文件名: {keep_file}")
    # print(f"警告: 这将删除所有子文件夹中除 '{keep_file}' 外的所有内容!")
    #
    # confirm = input("确认继续? (输入 'yes' 继续): ")
    #
    # if confirm.lower() == 'yes':
    #     delete_all_except(root_directory, keep_file)
    #     print("\n操作完成!")
    # else:
    #     print("操作已取消")

    gen_json(r'C:\workspace\share_all\yanhao\Sim\Contrast')