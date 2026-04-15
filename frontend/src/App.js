import { useState, useEffect, useCallback, useRef } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import axios from 'axios';
import '@/App.css';
import { Play, Pause, CaretLeft, CaretRight, Folder, FolderOpen, ArrowLeft, Spinner, ArrowClockwise } from '@phosphor-icons/react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const API_TIMEOUT_MS = 300000; // 5 minutes — large folders need time to scan
const AUTOPLAY_INTERVAL_MS = 5000;

/* ── Utility: Build folder tree from flat item list ── */
function buildFolderTree(data) {
  const folderMap = {};
  const folderOrder = [];

  data.items.forEach(item => {
    if (item.type === 'folder' && !folderMap[item.path]) {
      folderMap[item.path] = { name: item.name, path: item.path, images: [], depth: item.path.split('/').length - 1 };
      folderOrder.push(item.path);
    }
  });

  data.items.forEach(item => {
    if (item.type === 'image') {
      const parentPath = item.path.substring(0, item.path.lastIndexOf('/'));
      if (folderMap[parentPath]) {
        folderMap[parentPath].images.push(item);
      }
    }
  });

  const folderList = folderOrder.map(p => folderMap[p]).filter(Boolean);
  const topLevel = folderList.filter(f => f.depth === 0);

  return topLevel.map(top => {
    const allImages = [];
    folderList.forEach(f => {
      if (f.path === top.path || f.path.startsWith(top.path + '/')) {
        allImages.push(...f.images);
      }
    });
    const subfolders = folderList.filter(f => f.path.startsWith(top.path + '/') && f.images.length > 0);
    return { ...top, allImages, subfolders };
  });
}

/* ── Hook: Slideshow navigation ── */
function useSlideshow(imageCount) {
  const [imgIdx, setImgIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [imgErr, setImgErr] = useState(false);
  const timerRef = useRef(null);

  const next = useCallback(() => {
    if (imageCount === 0) return;
    setImgIdx(prev => (prev + 1) % imageCount);
    setImgErr(false);
  }, [imageCount]);

  const prev = useCallback(() => {
    if (imageCount === 0) return;
    setImgIdx(prev => (prev - 1 + imageCount) % imageCount);
    setImgErr(false);
  }, [imageCount]);

  const reset = useCallback(() => {
    setImgIdx(0);
    setImgErr(false);
    setIsPlaying(false);
  }, []);

  // Auto-play timer
  useEffect(() => {
    if (isPlaying && imageCount > 0) {
      timerRef.current = setInterval(next, AUTOPLAY_INTERVAL_MS);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isPlaying, next, imageCount]);

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight') next();
      else if (e.key === 'ArrowLeft') prev();
      else if (e.key === ' ') { e.preventDefault(); setIsPlaying(p => !p); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [next, prev]);

  return { imgIdx, isPlaying, setIsPlaying, imgErr, setImgErr, next, prev, reset };
}

/* ── Landing Page ── */
function LandingPage() {
  const navigate = useNavigate();
  const [driveLink, setDriveLink] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLoad = async () => {
    if (!driveLink.trim()) { toast.error('Please enter a Google Drive folder link'); return; }
    try {
      setLoading(true);
      toast.info('Scanning folder structure...');
      const res = await axios.post(`${API}/drive/folder`, { drive_link: driveLink }, { timeout: API_TIMEOUT_MS });
      localStorage.setItem('folder_data', JSON.stringify(res.data));
      localStorage.setItem('drive_link', driveLink);
      toast.success(`Found ${res.data.total_images} images in ${res.data.total_folders} folders!`);
      navigate('/slideshow');
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to access folder. Try again.");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-white flex items-center justify-center p-6" data-testid="landing-page">
      <div className="max-w-2xl w-full space-y-8">
        <div className="text-center space-y-4">
          <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl tracking-tighter font-black text-[#0A0A0A]" data-testid="landing-title">Drive Slideshow</h1>
          <p className="text-base leading-relaxed text-[#525252] max-w-xl mx-auto" data-testid="landing-subtitle">Paste your Google Drive folder link to browse folders and view images.</p>
        </div>
        <div className="bg-[#F2F2F2] border border-[#E5E5E5] p-8 space-y-4">
          <label className="text-xs uppercase tracking-[0.2em] font-bold text-[#0A0A0A]" data-testid="link-label">Google Drive Folder Link</label>
          <div className="flex gap-2">
            <Input data-testid="drive-link-input" placeholder="https://drive.google.com/drive/folders/..." value={driveLink} onChange={(e) => setDriveLink(e.target.value)} className="flex-1 rounded-sm border-[#E5E5E5] focus:border-[#0A0A0A] focus:ring-1 focus:ring-[#0A0A0A] font-body" onKeyDown={(e) => e.key === 'Enter' && !loading && handleLoad()} disabled={loading} />
            <Button data-testid="load-folder-button" onClick={handleLoad} disabled={loading} className="bg-[#002FA7] text-white hover:bg-[#002FA7]/90 rounded-sm px-6 font-body min-w-[120px]">
              {loading ? <Spinner className="w-4 h-4 animate-spin" /> : 'Load'}
            </Button>
          </div>
          <p className="text-xs text-[#525252] font-body">Folder must be shared publicly (Anyone with the link)</p>
        </div>
      </div>
    </div>
  );
}

/* ── Sidebar Component ── */
function Sidebar({ folderData, folders, selectedIdx, onSelectFolder, onRefresh, refreshing, onBack }) {
  return (
    <div className="w-72 border-r border-[#E5E5E5] flex flex-col h-full bg-white flex-shrink-0">
      <div className="p-5 border-b border-[#E5E5E5]">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-lg font-bold text-[#0A0A0A] tracking-tight truncate" data-testid="folder-title">{folderData.folder_name}</h2>
          <Button data-testid="refresh-button" onClick={onRefresh} disabled={refreshing} variant="ghost" size="icon" className="h-7 w-7 rounded-sm hover:bg-[#F2F2F2] flex-shrink-0" title="Refresh folder data">
            <ArrowClockwise className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} weight="bold" />
          </Button>
        </div>
        <p className="text-xs text-[#525252] mt-1 font-body">{folders.length} folders</p>
      </div>

      <ScrollArea className="flex-1" data-testid="folder-tree">
        <div className="py-2 px-2 space-y-1">
          {folders.map((folder, idx) => (
            <div
              key={folder.path}
              data-testid={`folder-item-${idx}`}
              onClick={() => onSelectFolder(idx)}
              className={`flex items-center gap-2 px-3 py-3 rounded-sm cursor-pointer transition-all duration-150 ${
                idx === selectedIdx ? 'bg-[#002FA7] text-white' : 'text-[#0A0A0A] hover:bg-[#F2F2F2]'
              }`}
            >
              {idx === selectedIdx
                ? <FolderOpen className="w-5 h-5 flex-shrink-0" weight="fill" />
                : <Folder className="w-5 h-5 flex-shrink-0" weight="fill" />}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-body font-medium truncate">{folder.name}</p>
                <p className={`text-[11px] ${idx === selectedIdx ? 'text-white/60' : 'text-[#525252]'}`}>
                  {folder.allImages.length} images
                  {folder.subfolders.length > 0 && ` / ${folder.subfolders.length} sections`}
                </p>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>

      <div className="p-4 border-t border-[#E5E5E5]">
        <Button data-testid="back-button" onClick={onBack} variant="outline" className="w-full rounded-sm font-body text-sm">
          <ArrowLeft className="w-4 h-4 mr-2" /> New Folder
        </Button>
      </div>
    </div>
  );
}

/* ── Image Viewer Component ── */
function ImageViewer({ images, imgIdx, imgErr, setImgErr, subfolder, currentImg, progress, isPlaying, setIsPlaying, next, prev }) {
  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="h-1 bg-[#E5E5E5] w-full flex-shrink-0">
        <div className="h-full bg-[#002FA7] progress-bar" style={{ width: `${progress}%` }} data-testid="progress-bar" />
      </div>

      <div className="flex-1 relative bg-[#0A0A0A] min-h-0" data-testid="slideshow-container">
        {images.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Folder className="w-12 h-12 text-white/20 mx-auto mb-2" weight="fill" />
              <p className="text-white/40 font-body text-sm">Select a folder</p>
            </div>
          </div>
        ) : currentImg && (
          !imgErr ? (
            <img key={currentImg.id} src={`${API}/drive/image/${currentImg.id}`} alt={currentImg.name} className="absolute inset-0 w-full h-full object-contain slide-image bg-[#0A0A0A]" data-testid="slideshow-image" onError={() => setImgErr(true)} />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-[#111]">
              <p className="text-white/30 font-body">Failed to load image</p>
            </div>
          )
        )}
      </div>

      {/* Bottom bar */}
      <div className="flex-shrink-0 bg-[#0A0A0A] border-t border-[#222] flex items-center justify-between px-4 py-2" data-testid="slideshow-controls">
        <div className="flex-1 min-w-0 mr-4">
          <p className="font-body font-medium text-white truncate" style={{ fontSize: '14px' }} data-testid="folder-name-overlay">{subfolder}</p>
          {currentImg && <p className="font-body text-white/50 truncate" style={{ fontSize: '12px' }}>{currentImg.name}</p>}
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <Button data-testid="previous-button" onClick={prev} variant="ghost" size="icon" className="rounded-sm hover:bg-white/10 h-8 w-8 text-white" disabled={images.length === 0}><CaretLeft className="w-5 h-5" weight="bold" /></Button>
          <Button data-testid="play-pause-button" onClick={() => setIsPlaying(!isPlaying)} variant="ghost" size="icon" className="rounded-sm hover:bg-white/10 h-8 w-8 text-white" disabled={images.length === 0}>
            {isPlaying ? <Pause className="w-5 h-5" weight="fill" /> : <Play className="w-5 h-5" weight="fill" />}
          </Button>
          <Button data-testid="next-button" onClick={next} variant="ghost" size="icon" className="rounded-sm hover:bg-white/10 h-8 w-8 text-white" disabled={images.length === 0}><CaretRight className="w-5 h-5" weight="bold" /></Button>
          <div className="h-4 w-px bg-white/20" />
          <span className="text-xs font-body text-white/70 tabular-nums" data-testid="slide-counter">{images.length > 0 ? `${imgIdx + 1} / ${images.length}` : '0 / 0'}</span>
        </div>
      </div>
    </div>
  );
}

/* ── Slideshow Page ── */
function SlideshowPage() {
  const navigate = useNavigate();
  const [folderData, setFolderData] = useState(null);
  const [folders, setFolders] = useState([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [images, setImages] = useState([]);
  const [refreshing, setRefreshing] = useState(false);

  const slideshow = useSlideshow(images.length);

  // Load folder data on mount
  useEffect(() => {
    const raw = localStorage.getItem('folder_data');
    if (!raw) { navigate('/'); return; }
    const data = JSON.parse(raw);
    setFolderData(data);
    const enriched = buildFolderTree(data);
    setFolders(enriched);
    if (enriched.length > 0) {
      setImages(enriched[0].allImages);
      setSelectedIdx(0);
    }
  }, [navigate]);

  const selectFolder = useCallback((idx) => {
    setSelectedIdx(idx);
    setImages(prev => {
      const newImages = folders[idx]?.allImages || [];
      return newImages;
    });
    slideshow.reset();
  }, [folders, slideshow]);

  const handleRefresh = async () => {
    const link = localStorage.getItem('drive_link');
    if (!link) return;
    try {
      setRefreshing(true);
      toast.info('Refreshing folder data...');
      const res = await axios.post(`${API}/drive/folder?refresh=true`, { drive_link: link }, { timeout: API_TIMEOUT_MS });
      localStorage.setItem('folder_data', JSON.stringify(res.data));
      setFolderData(res.data);
      const enriched = buildFolderTree(res.data);
      setFolders(enriched);
      if (enriched.length > 0) {
        setSelectedIdx(0);
        setImages(enriched[0].allImages);
        slideshow.reset();
      }
      toast.success(`Refreshed! ${res.data.total_images} images in ${res.data.total_folders} folders`);
    } catch (err) {
      toast.error('Refresh failed. Try again.');
    } finally { setRefreshing(false); }
  };

  const handleBack = useCallback(() => {
    localStorage.removeItem('folder_data');
    navigate('/');
  }, [navigate]);

  if (!folderData) {
    return <div className="h-screen flex items-center justify-center bg-white"><Spinner className="w-8 h-8 animate-spin text-[#002FA7]" /></div>;
  }

  const currentImg = images[slideshow.imgIdx];
  const progress = images.length > 0 ? ((slideshow.imgIdx + 1) / images.length) * 100 : 0;
  const subfolder = currentImg ? currentImg.path.substring(0, currentImg.path.lastIndexOf('/')) : '';

  return (
    <div className="h-screen flex overflow-hidden bg-white" data-testid="slideshow-page">
      <Sidebar
        folderData={folderData}
        folders={folders}
        selectedIdx={selectedIdx}
        onSelectFolder={selectFolder}
        onRefresh={handleRefresh}
        refreshing={refreshing}
        onBack={handleBack}
      />
      <ImageViewer
        images={images}
        imgIdx={slideshow.imgIdx}
        imgErr={slideshow.imgErr}
        setImgErr={slideshow.setImgErr}
        subfolder={subfolder}
        currentImg={currentImg}
        progress={progress}
        isPlaying={slideshow.isPlaying}
        setIsPlaying={slideshow.setIsPlaying}
        next={slideshow.next}
        prev={slideshow.prev}
      />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/slideshow" element={<SlideshowPage />} />
      </Routes>
    </BrowserRouter>
  );
}
