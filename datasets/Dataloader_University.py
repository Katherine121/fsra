import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from torch.utils.data.sampler import Sampler
from torchvision import datasets, transforms
import os
import numpy as np
from PIL import Image


from collections import OrderedDict

import math
import os
import random

import torch
from PIL import Image
from torch.utils.data import Dataset


class OrderTrainDataset(Dataset):
    def __init__(self, dataset_path, class_path, k, transforms_drone_street):
        """
        train dataset, form a sequence every five frames with an end point frame.
        :param transform: torchvision.transforms.
        :param input_len: input sequence length (not containing the end point).
        """
        self.transforms_drone_street = transforms_drone_street
        self.cls_names = []

        res = []
        new_res = []
        for j in range(0, k):
            res.append([])
            self.cls_names.append(j)

        dir_path1 = os.listdir(dataset_path)
        dir_path1.sort()

        class_path1 = os.listdir(class_path)
        class_path1.sort()

        for i in range(0, len(dir_path1)):
            if i % 5 != 0:
                dir1 = dir_path1[i]
                full_dir_path = os.path.join(dataset_path, dir1)

                file_path1 = os.listdir(full_dir_path)
                file_path1.sort()

                f = open(class_path + "/" + class_path1[i])
                cluster_labels = []
                for line in f:
                    line = line.strip('\n')
                    cluster_labels.append(int(line))

                for j in range(0, len(file_path1)):
                    file1 = file_path1[j]
                    full_file_path = os.path.join(full_dir_path, file1)
                    res[cluster_labels[j]].append(full_file_path)

        for i in range(0, k):
            for p in range(0, len(res[i])):
                random_index1 = random.randint(a=0, b=len(res[i]) - 1)
                random_index2 = random.randint(a=0, b=len(res[i]) - 1)
                new_res.append([res[i][p], res[i][random_index1], res[i][random_index2], i])
        print(len(new_res))
        self.imgs = new_res

    def __len__(self):
        """
        return the length of the dataset.
        :return:
        """
        return len(self.imgs)

    def __getitem__(self, index):
        """
        read the image sequence, angle sequence and label corresponding to the index in the dataset.
        :param index: index of self.imgs.
        :return: frame sequence, angle sequence,
                the current position label, the next position label, the direction angle.
        """
        imgs = self.imgs[index]

        img1 = Image.open(imgs[0])
        img1 = img1.convert('RGB')
        img1 = self.transforms_drone_street(img1)

        img2 = Image.open(imgs[1])
        img2 = img2.convert('RGB')
        img2 = self.transforms_drone_street(img2)

        img3 = Image.open(imgs[2])
        img3 = img3.convert('RGB')
        img3 = self.transforms_drone_street(img3)

        label = imgs[3]

        return img1, img2, img3, torch.tensor(label, dtype=torch.int64)


class OrderTestDataset(Dataset):
    def __init__(self, dataset_path, class_path, k, transforms_drone_street):
        """
        train dataset, form a sequence every five frames with an end point frame.
        :param transform: torchvision.transforms.
        :param input_len: input sequence length (not containing the end point).
        """
        self.transforms_drone_street = transforms_drone_street
        self.cls_names = []

        res = []
        new_res = []
        for j in range(0, k):
            res.append([])
            self.cls_names.append(j)

        dir_path1 = os.listdir(dataset_path)
        dir_path1.sort()

        class_path1 = os.listdir(class_path)
        class_path1.sort()

        for i in range(0, len(dir_path1)):
            if i % 5 == 0:
                dir1 = dir_path1[i]
                full_dir_path = os.path.join(dataset_path, dir1)

                file_path1 = os.listdir(full_dir_path)
                file_path1.sort()

                f = open(class_path + "/" + class_path1[i])
                cluster_labels = []
                for line in f:
                    line = line.strip('\n')
                    cluster_labels.append(int(line))

                for j in range(0, len(file_path1)):
                    file1 = file_path1[j]
                    full_file_path = os.path.join(full_dir_path, file1)
                    res[cluster_labels[j]].append(full_file_path)

        for i in range(0, k):
            for p in range(0, len(res[i])):
                random_index1 = random.randint(a=0, b=len(res[i]) - 1)
                random_index2 = random.randint(a=0, b=len(res[i]) - 1)
                new_res.append([res[i][p], res[i][random_index1], res[i][random_index2], i])
        print(len(new_res))
        self.imgs = new_res

    def __len__(self):
        """
        return the length of the dataset.
        :return:
        """
        return len(self.imgs)

    def __getitem__(self, index):
        """
        read the image sequence, angle sequence and label corresponding to the index in the dataset.
        :param index: index of self.imgs.
        :return: frame sequence, angle sequence,
                the current position label, the next position label, the direction angle.
        """
        imgs = self.imgs[index]

        img1 = Image.open(imgs[0])
        img1 = img1.convert('RGB')
        img1 = self.transforms_drone_street(img1)

        img2 = Image.open(imgs[1])
        img2 = img2.convert('RGB')
        img2 = self.transforms_drone_street(img2)

        img3 = Image.open(imgs[2])
        img3 = img3.convert('RGB')
        img3 = self.transforms_drone_street(img3)

        label = imgs[3]

        return img1, img2, img3, torch.tensor(label, dtype=torch.int64)


class Dataloader_University(Dataset):
    def __init__(self,root,transforms,names=['satellite','street','drone','google']):
        super(Dataloader_University).__init__()
        self.transforms_drone_street = transforms['train']
        self.transforms_satellite = transforms['satellite']
        self.root = root
        self.names =  names
        #获取所有图片的相对路径分别放到对应的类别中
        #{satelite:{0839:[0839.jpg],0840:[0840.jpg]}}
        dict_path = {}
        for name in names:
            dict_ = {}
            for cls_name in os.listdir(os.path.join(root, name)):
                img_list = os.listdir(os.path.join(root,name,cls_name))
                img_path_list = [os.path.join(root,name,cls_name,img) for img in img_list]
                dict_[cls_name] = img_path_list
            dict_path[name] = dict_
            # dict_path[name+"/"+cls_name] = img_path_list

        #获取设置名字与索引之间的镜像
        cls_names = os.listdir(os.path.join(root,names[0]))
        cls_names.sort()
        map_dict={i:cls_names[i] for i in range(len(cls_names))}

        self.cls_names = cls_names
        self.map_dict = map_dict
        self.dict_path = dict_path
        self.index_cls_nums = 2

    #从对应的类别中抽一张出来
    def sample_from_cls(self,name,cls_num):
        img_path = self.dict_path[name][cls_num]
        img_path = np.random.choice(img_path,1)[0]
        img = Image.open(img_path)
        return img


    def __getitem__(self, index):
        cls_nums = self.map_dict[index]
        img = self.sample_from_cls("satellite",cls_nums)
        img_s = self.transforms_satellite(img)

        img = self.sample_from_cls("street",cls_nums)
        img_st = self.transforms_drone_street(img)

        img = self.sample_from_cls("drone",cls_nums)
        img_d = self.transforms_drone_street(img)
        return img_s,img_st,img_d,index


    def __len__(self):
        return len(self.cls_names)



class Sampler_University(object):
    r"""Base class for all Samplers.
    Every Sampler subclass has to provide an :meth:`__iter__` method, providing a
    way to iterate over indices of dataset elements, and a :meth:`__len__` method
    that returns the length of the returned iterators.
    .. note:: The :meth:`__len__` method isn't strictly required by
              :class:`~torch.utils.data.DataLoader`, but is expected in any
              calculation involving the length of a :class:`~torch.utils.data.DataLoader`.
    """

    def __init__(self, data_source, batchsize=8,sample_num=4):
        self.data_len = len(data_source)
        self.batchsize = batchsize
        self.sample_num = sample_num

    def __iter__(self):
        list = np.arange(0,self.data_len)
        np.random.shuffle(list)
        nums = np.repeat(list,self.sample_num,axis=0)
        return iter(nums)

    def __len__(self):
        return len(self.data_source)


def train_collate_fn(batch):
    """
    # collate_fn这个函数的输入就是一个list，list的长度是一个batch size，list中的每个元素都是__getitem__得到的结果
    """
    img_s,img_st,img_d,ids = zip(*batch)
    ids = torch.tensor(ids,dtype=torch.int64)
    return [torch.stack(img_s, dim=0),ids],[torch.stack(img_st,dim=0),ids], [torch.stack(img_d,dim=0),ids]

if __name__ == '__main__':
    transform_train_list = [
        # transforms.RandomResizedCrop(size=(opt.h, opt.w), scale=(0.75,1.0), ratio=(0.75,1.3333), interpolation=3), #Image.BICUBIC)
        transforms.Resize((256, 256), interpolation=3),
        transforms.Pad(10, padding_mode='edge'),
        transforms.RandomCrop((256, 256)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]


    transform_train_list ={"satellite": transforms.Compose(transform_train_list),
                            "train":transforms.Compose(transform_train_list)}
    # datasets = Dataloader_University(root="/home/dmmm/University-Release/train",transforms=transform_train_list,names=['satellite','drone'])
    samper = Sampler_University(datasets,8)
    dataloader = DataLoader(datasets,batch_size=8,num_workers=0,sampler=samper,collate_fn=train_collate_fn)
    for data_s,data_d in dataloader:
        print()


