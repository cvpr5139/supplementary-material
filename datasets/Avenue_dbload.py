from torch.utils.data import Dataset
from os.path import join
from os.path import basename
from os.path import isdir
from glob import glob
import numpy as np
import skimage.io as io
from scipy.io import loadmat
from skimage.transform import resize
from torch.utils.data.dataloader import default_collate

from torchvision import transforms
from datasets.transforms import ToFloatTensor3D, ToCenterCrops, ToSpatialCrops, Normalize

def default_list_reader(fileList):
    imgList = []
    with open(fileList, 'r') as file:
        for line in file.readlines():
            dir, img = line.strip().split(' ')
            imgList.append((dir, img))
    return imgList

class Avenue(Dataset):
    def __init__(self, args, train):
        self.path = args.datapath
        self.videoshape = args.videoshape
        self.train = train
        self.dataset = args.dataset

        if self.train:
            self.trainlist = './datasets/' + str(args.dataset) + '_%d' % (args.cropshape[1]) + '.txt'
            self.imglist = default_list_reader(self.trainlist)
            self.train_dir = join(self.path, args.dataset, 'training')
            self.train_transform = transforms.Compose([ToFloatTensor3D(), Normalize(), ToSpatialCrops(args.videoshape, args.cropshape)])
        else:
            self.test_dir = join(self.path, args.dataset, 'testing')
            self.cur_video_id = None
            self.cur_video_frames = None
            self.cur_video_gt = None
            self.cur_background = None
            self.cur_len = 0
            self.test_transform = transforms.Compose([ToFloatTensor3D(), Normalize(), ToCenterCrops(args.videoshape, args.cropshape)])

    def load_ids(self, path):
        return sorted([basename(d) for d in glob(join(path, 'frames', '**')) if isdir(d)])

    def load_clip(self, path, video_id):
        c, t, h, w = self.videoshape

        sequence_dir = join(path,'frames',  video_id)
        img_list = sorted(glob(join(sequence_dir, '*.jpg')))
        clip = []
        for img_path in img_list:
            img = io.imread(img_path)
            img = resize(img, output_shape=(h, w), preserve_range=True)
            img = np.uint8(img)
            clip.append(img)
        clip = np.stack(clip)
        return clip

    def loader(self, dir, img):
        C, T, H, W = self.videoshape
        img_path = join(self.path, self.dataset, 'training/frames', dir)

        img_num = int(img)
        segment = []
        for t in range(T):
            img = io.imread(join(img_path, "%04d" % (img_num+t) + '.jpg'))
            img = resize(img, output_shape=(H, W), preserve_range=True)
            img = np.uint8(img)
            segment.append(img)
        segment = np.stack(segment)
        return segment

    @property
    def test_videos(self):
        return self.load_ids(self.test_dir)

    @property
    def val_videos(self):
        test =  self.test_videos
        val = []
        for i in range(len(test)):
            if int(i%2) == 0:
                val.append(test[i])
        return val

    def load_test_sequence_gt(self, video_id):
        frame_list = loadmat(join(self.test_dir, 'gt', video_id + '_label.mat'))
        clip_gt = []
        mat_file = frame_list['volLabel']
        for i in range(mat_file.shape[1]):
            mask = mat_file[0, i]
            clip_gt.append(np.max(mask))  # if at least one pixel is 1, then anomaly
        clip_gt = np.stack(clip_gt)
        return clip_gt

    def test(self, video_id):
        c, t, h, w = self.videoshape

        self.cur_video_id = video_id
        self.cur_video_gt = self.load_test_sequence_gt(video_id)
        self.cur_video_frames = self.load_clip(self.test_dir, video_id)

        self.cur_len = len(self.cur_video_frames) - t + 1


    def __getitem__(self, idx):
        c, t, h, w = self.videoshape
        if self.train:
            dir, img = self.imglist[idx]
            segments = self.loader(dir, img)  # T, H, W, C
            sample = segments, segments
            samples_trans = self.train_transform(sample)

            return samples_trans
        else:
            clip = self.cur_video_frames[idx:idx + t]
            sample = clip, clip
            clip_trans = self.test_transform(sample)

            return clip_trans
    def __len__(self):
        if self.train:
            return len(self.imglist)
        else:
            return self.cur_len

    @property
    def collate_fn(self):
        return default_collate

