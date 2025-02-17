# -*- coding: utf-8 -*-

from __future__ import print_function, division
import argparse
import torch
import torch.nn as nn

from torch.autograd import Variable
from torch.cuda.amp import autocast,GradScaler
import torch.backends.cudnn as cudnn
import time
from optimizers.make_optimizer import make_optimizer
from models.model import make_model
from datasets.make_dataloader import make_dataset
from tool.utils_server import save_network,copyfiles2checkpoints
import warnings
from losses.triplet_loss import Tripletloss,TripletLoss
from losses.cal_loss import cal_kl_loss,cal_loss,cal_triplet_loss

warnings.filterwarnings("ignore")
version =  torch.__version__
#fp16
try:
    from apex.fp16_utils import *
    from apex import amp, optimizers
except ImportError: # will be 3.x series
    print('This is not an error. If you want to use low precision, i.e., fp16, please install the apex with cuda support (https://github.com/NVIDIA/apex) and update pytorch to 1.0')
######################################################################
# Options
# --------

def get_parse():
    parser = argparse.ArgumentParser(description='Training')
    parser.add_argument('--gpu_ids',default='0', type=str,help='gpu_ids: e.g. 0  0,1,2  0,2')
    parser.add_argument('--name',default='test', type=str, help='output model name')
    parser.add_argument('--data_dir',default='/home/dmmm/University-Release/train',type=str, help='training dir path')
    parser.add_argument('--dataset_path',type=str, help='training dir path')
    parser.add_argument('--class_path',type=str, help='training dir path')
    parser.add_argument('--k',type=int, help='training dir path')
    parser.add_argument('--train_all', action='store_true', help='use all training data' )
    parser.add_argument('--color_jitter', action='store_true', help='use color jitter in training' )
    parser.add_argument('--num_worker', default=4,type=int, help='' )
    parser.add_argument('--batchsize', default=8, type=int, help='batchsize')
    parser.add_argument('--pad', default=0, type=int, help='padding')
    parser.add_argument('--h', default=256, type=int, help='height')
    parser.add_argument('--w', default=256, type=int, help='width')
    parser.add_argument('--views', default=2, type=int, help='the number of views')
    parser.add_argument('--erasing_p', default=0, type=float, help='Random Erasing probability, in [0,1]')
    parser.add_argument('--warm_epoch', default=0, type=int, help='the first K epoch that needs warm up')
    parser.add_argument('--lr', default=0.01, type=float, help='learning rate')
    parser.add_argument('--moving_avg', default=1.0, type=float, help='moving average')
    parser.add_argument('--DA', action='store_true', help='use Color Data Augmentation' )
    parser.add_argument('--share', action='store_true',default=True, help='share weight between different view' )
    parser.add_argument('--fp16', action='store_true',default=False, help='use float16 instead of float32, which will save about 50% memory' )
    parser.add_argument('--autocast', action='store_true',default=True, help='use mix precision' )
    parser.add_argument('--block', default=3, type=int, help='')
    parser.add_argument('--kl_loss', action='store_true',default=False, help='kl_loss' )
    parser.add_argument('--triplet_loss', default=0.3, type=float, help='')
    parser.add_argument('--sample_num', default=1, type=float, help='num of repeat sampling' )
    parser.add_argument('--num_epochs', default=120, type=int, help='' )
    parser.add_argument('--steps', default=[70,110], type=int, help='' )
    opt = parser.parse_args()
    return opt


def train_model(model,opt, optimizer, scheduler, dataloaders,dataset_sizes):
    use_gpu = opt.use_gpu
    num_epochs = opt.num_epochs

    since = time.time()
    warm_up = 0.1  # We start from the 0.1*lrRate
    warm_iteration = round(dataset_sizes['satellite'] / opt.batchsize) * opt.warm_epoch  # first 5 epoch

    scaler = GradScaler()
    criterion = nn.CrossEntropyLoss()
    loss_kl = nn.KLDivLoss(reduction='batchmean')
    triplet_loss = Tripletloss(margin=opt.triplet_loss)
    best_acc = 0

    for epoch in range(num_epochs):
        total_loss = 0
        print('Epoch {}/{}'.format(epoch, num_epochs - 1))
        print('-' * 10)

        # Each epoch has a training and validation phase
        for phase in ['train']:
            if phase == 'train':
                model.train(True)  # Set model to training mode
            else:
                model.train(False)  # Set model to evaluate mode

            running_cls_loss = 0.0
            running_triplet = 0.0
            running_kl_loss = 0.0
            running_loss = 0.0
            running_corrects = 0.0
            running_corrects2 = 0.0
            running_corrects3 = 0.0

            for iter, (inputs,inputs2,inputs3,labels) in enumerate(dataloaders):
                # satallite # street # drone
                loss = 0.0
                # get the inputs
                labels2 = labels
                labels3 = labels
                now_batch_size, c, h, w = inputs.size()
                if now_batch_size < opt.batchsize:  # skip the last batch
                    continue
                if use_gpu:
                    inputs = Variable(inputs.cuda().detach())
                    inputs2 = Variable(inputs2.cuda().detach())
                    inputs3 = Variable(inputs3.cuda().detach())
                    labels = Variable(labels.cuda().detach())
                    labels2 = Variable(labels2.cuda().detach())
                    labels3 = Variable(labels3.cuda().detach())
                else:
                    inputs, labels = Variable(inputs), Variable(labels)

                # zero the parameter gradients
                optimizer.zero_grad()

                # forward
                if phase == 'val':
                    with torch.no_grad():
                        outputs, outputs2 = model(inputs, inputs3)
                else:
                    if opt.views == 2:
                        with autocast():
                            outputs, outputs2 = model(inputs, inputs3) # satellite and drone
                    elif opt.views == 3:
                        outputs, outputs2, outputs3 = model(inputs, inputs2, inputs3)
                f_triplet_loss=torch.tensor((0))
                if opt.triplet_loss>0:
                    features = outputs[1]
                    features2 = outputs2[1]
                    split_num = opt.batchsize//opt.sample_num
                    f_triplet_loss = cal_triplet_loss(features,features2,labels,triplet_loss,split_num)

                    outputs = outputs[0]
                    outputs2 = outputs2[0]

                if isinstance(outputs,list):
                    preds = []
                    preds2 = []
                    for out,out2 in zip(outputs,outputs2):
                        preds.append(torch.max(out.data,1)[1])
                        preds2.append(torch.max(out2.data,1)[1])
                else:
                    _, preds = torch.max(outputs.data, 1)
                    _, preds2 = torch.max(outputs2.data, 1)
                kl_loss = torch.tensor((0))
                if opt.views == 2:
                    cls_loss = cal_loss(outputs, labels,criterion) + cal_loss(outputs2, labels3,criterion) # only compute the global branch
                    #增加klLoss来做mutual learning
                    if opt.kl_loss:
                        kl_loss = cal_kl_loss(outputs,outputs2,loss_kl)

                elif opt.views == 3:
                    if isinstance(outputs,list):
                        preds3 = []
                        for out3 in outputs3:
                            preds3.append(torch.max(out3.data,1)[1])
                        cls_loss = cal_loss(outputs, labels,criterion) + cal_loss(outputs2, labels2,criterion) + cal_loss(outputs3, labels3,criterion)
                        loss+=cls_loss

                    else:
                        _, preds3 = torch.max(outputs3.data, 1)
                        cls_loss = cal_loss(outputs, labels,criterion) + cal_loss(outputs2, labels2,criterion) + cal_loss(outputs3, labels3,criterion)
                        loss+=cls_loss

                loss = kl_loss + cls_loss + f_triplet_loss
                # backward + optimize only if in training phase
                if epoch < opt.warm_epoch and phase == 'train':
                    warm_up = min(1.0, warm_up + 0.9 / warm_iteration)
                    loss *= warm_up

                total_loss += loss
                if phase == 'train':
                    if opt.autocast:
                        scaler.scale(loss).backward()
                        scaler.step(optimizer)
                        scaler.update()
                    else:
                        loss.backward()
                        optimizer.step()

                # statistics
                if int(version[0]) > 0 or int(version[2]) > 3:  # for the new version like 0.4.0, 0.5.0 and 1.0.0
                    running_loss += loss.item() * now_batch_size
                    running_cls_loss += cls_loss.item()*now_batch_size
                    running_triplet += f_triplet_loss.item() * now_batch_size
                    running_kl_loss += kl_loss.item() * now_batch_size
                else:  # for the old version like 0.3.0 and 0.3.1
                    running_loss += loss.data[0] * now_batch_size
                    running_cls_loss += cls_loss.data[0] * now_batch_size
                    running_triplet += f_triplet_loss.data[0] * now_batch_size
                    running_kl_loss += kl_loss.data[0] * now_batch_size


                if isinstance(preds,list) and isinstance(preds2,list):
                    running_corrects += sum([float(torch.sum(pred == labels.data)) for pred in preds])/len(preds)
                    if opt.views==2:
                        running_corrects2 += sum([float(torch.sum(pred == labels3.data)) for pred in preds2]) / len(preds2)
                    else:
                        running_corrects2 += sum([float(torch.sum(pred == labels2.data)) for pred in preds2])/len(preds2)
                else:
                    running_corrects += float(torch.sum(preds == labels.data))
                    if opt.views == 2:
                        running_corrects2 += float(torch.sum(preds2 == labels3.data))
                    else:
                        running_corrects2 += float(torch.sum(preds2 == labels2.data))
                if opt.views == 3:
                    if isinstance(preds,list) and isinstance(preds2,list):
                        running_corrects3 += sum([float(torch.sum(pred == labels3.data)) for pred in preds3])/len(preds3)
                    else:
                        running_corrects3 += float(torch.sum(preds3 == labels3.data))

                if iter % 100 == 0:
                    print("loss:" + str(loss.item()))
            epoch_cls_loss = running_cls_loss/dataset_sizes['satellite']
            epoch_kl_loss = running_kl_loss /dataset_sizes['satellite']
            epoch_triplet_loss = running_triplet/dataset_sizes['satellite']
            epoch_loss = running_loss / dataset_sizes['satellite']
            epoch_acc = running_corrects / dataset_sizes['satellite']
            epoch_acc2 = running_corrects2 / dataset_sizes['satellite']


            lr_backbone = optimizer.state_dict()['param_groups'][0]['lr']
            lr_other = optimizer.state_dict()['param_groups'][1]['lr']
            if opt.views == 2:
                print(
                    '{} Loss: {:.4f} Cls_Loss:{:.4f} KL_Loss:{:.4f} Triplet_Loss {:.4f} Satellite_Acc: {:.4f}  Drone_Acc: {:.4f} lr_backbone:{:.6f} lr_other {:.6f}'
                                                                                .format(phase, epoch_loss,epoch_cls_loss,epoch_kl_loss,
                                                                                        epoch_triplet_loss, epoch_acc,
                                                                                        epoch_acc2,lr_backbone,lr_other))
            elif opt.views == 3:
                epoch_acc3 = running_corrects3 / dataset_sizes['satellite']
                print('{} Loss: {:.4f} Satellite_Acc: {:.4f}  Street_Acc: {:.4f} Drone_Acc: {:.4f}'.format(phase,
                                                                                                           epoch_loss,
                                                                                                           epoch_acc,
                                                                                                           epoch_acc2,
                                                                                                           epoch_acc3))

            # deep copy the model
            if phase == 'train':
                scheduler.step()

            avg_loss = total_loss / (iter + 1)
            avg_acc = (epoch_acc + epoch_acc2) / 2
            with open("save/loss.txt", "a") as file1:
                file1.write(str(avg_loss.item()) + "\n")
            file1.close()
            with open("save/acc.txt", "a") as file1:
                file1.write(str(avg_acc) + " " + str(epoch_acc) + " " + str(epoch_acc2) + " " + str(best_acc) + "\n")
            file1.close()
            torch.save(model, "checkpoint.pth.tar")
            if epoch_acc >= best_acc:
                torch.save(model, "save/best.pth.tar")

        time_elapsed = time.time() - since
        print('Training complete in {:.0f}m {:.0f}s'.format(
            time_elapsed // 60, time_elapsed % 60))
        print()


if __name__ == '__main__':
    opt = get_parse()
    str_ids = opt.gpu_ids.split(',')
    gpu_ids = []
    for str_id in str_ids:
        gid = int(str_id)
        if gid >= 0:
            gpu_ids.append(gid)

    use_gpu = torch.cuda.is_available()
    opt.use_gpu = use_gpu
    # set gpu ids
    if len(gpu_ids) > 0:
        torch.cuda.set_device(gpu_ids[0])
        cudnn.benchmark = True

    dataloaders,class_names,dataset_sizes = make_dataset(opt)
    opt.nclasses = len(class_names)

    model = make_model(opt)

    optimizer_ft, exp_lr_scheduler = make_optimizer(model,opt)
    model = model.cuda()
    #移动文件到指定文件夹
    copyfiles2checkpoints(opt)

    if opt.fp16:
        model, optimizer_ft = amp.initialize(model, optimizer_ft, opt_level="O1")

    print("start trainig")
    train_model(model,opt, optimizer_ft, exp_lr_scheduler,dataloaders,dataset_sizes)
