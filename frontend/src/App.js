import React, { useState, useEffect, useCallback, useRef } from 'react';
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom';
import axios from 'axios';
import '@/App.css';
import {
  Play,
  Pause,
  CaretLeft,
  CaretRight,
  Folder,
  Image as ImageIcon,
  ArrowLeft,
  Spinner
} from '@phosphor-icons/react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const FALLBACK_IMAGES = [
  "https://images.unsplash.com/photo-1567010375323-647e954af519?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2OTV8MHwxfHNlYXJjaHwyfHx3aGl0ZSUyMG1pbmltYWxpc3QlMjB0ZXh0dXJlfGVufDB8fHx3aGl0ZXwxNzc2MjI0ODg5fDA&ixlib=rb-4.1.0&q=85",
  "https://images.unsplash.com/photo-1584610559454-14c70cd3b869?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA6OTV8MHwxfHNlYXJjaHwzfHx3aGl0ZSUyMG1pbmltYWxpc3QlMjB0ZXh0dXJlfGVufDB8fHx3aGl0ZXwxNzc2MjI0ODg5fDA&ixlib=rb-4.1.0&q=85",
  "https://images.unsplash.com/photo-1627810872480-ed5d132a77a9?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2OTV8MHwxfHNlYXJjaHw0fHx3aGl0ZSUyMG1pbmltYWxpc3QlMjB0ZXh0dXJlfGVufDB8fHx3aGl0ZXwxNzc2MjI0ODg5fDA&ixlib=rb-4.1.0&q=85",
  "https://images.unsplash.com/photo-1548685913-fe6678babe8d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2OTV8MHwxfHNlYXJjaHwxfHx3aGl0ZSUyMG1pbmltYWxpc3QlMjB0ZXh0dXJlfGVufDB8fHx3aGl0ZXwxNzc2MjI0ODg5fDA&ixlib=rb-4.1.0&q=85"
];

const LandingPage = () => {
  const navigate = useNavigate();
  const [driveLink, setDriveLink] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLoadFolder = async () => {
    if (!driveLink.trim()) {
      toast.error('Please enter a Google Drive folder link');
      return;
    }

    try {
      setLoading(true);
      toast.info('Scanning folder structure... This may take a moment.');

      const response = await axios.post(`${API}/drive/folder`, {
        drive_link: driveLink
      });

      localStorage.setItem('folder_data', JSON.stringify(response.data));
      localStorage.setItem('drive_link', driveLink);

      toast.success(`Found ${response.data.total_images} images in ${response.data.total_folders} folders!`);
      navigate('/slideshow');
    } catch (error) {
      console.error('Folder fetch error:', error);
      toast.error(error.response?.data?.detail || 'Failed to access folder. Make sure it\'s shared publicly.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white flex items-center justify-center p-6" data-testid="landing-page">
      <div className="max-w-2xl w-full space-y-8">
        {/* Header */}
        <div className="text-center space-y-4">
          <h1
            className="font-heading text-4xl sm:text-5xl lg:text-6xl tracking-tighter font-black text-[#0A0A0A]"
            data-testid="landing-title"
          >
            Drive Slideshow
          </h1>
          <p className="text-base leading-relaxed text-[#525252] max-w-xl mx-auto" data-testid="landing-subtitle">
            Paste your Google Drive folder link to view all images as a beautiful slideshow with folder names overlaid.
          </p>
        </div>

        {/* Main Card */}
        <div className="bg-[#F2F2F2] border border-[#E5E5E5] p-8 space-y-6">
          <div className="space-y-3">
            <label className="text-xs uppercase tracking-[0.2em] font-bold text-[#0A0A0A]" data-testid="link-label">
              Google Drive Folder Link
            </label>
            <div className="flex gap-2">
              <Input
                data-testid="drive-link-input"
                type="text"
                placeholder="https://drive.google.com/drive/folders/..."
                value={driveLink}
                onChange={(e) => setDriveLink(e.target.value)}
                className="flex-1 rounded-sm border-[#E5E5E5] focus:border-[#0A0A0A] focus:ring-1 focus:ring-[#0A0A0A] font-body"
                onKeyDown={(e) => e.key === 'Enter' && !loading && handleLoadFolder()}
                disabled={loading}
              />
              <Button
                data-testid="load-folder-button"
                onClick={handleLoadFolder}
                disabled={loading}
                className="bg-[#002FA7] text-white hover:bg-[#002FA7]/90 rounded-sm px-6 font-body min-w-[120px]"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <Spinner className="w-4 h-4 animate-spin" />
                    Scanning...
                  </span>
                ) : (
                  'Load'
                )}
              </Button>
            </div>
            <p className="text-xs text-[#525252] font-body">
              The folder must be shared publicly (Anyone with the link can view)
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center">
          <p className="text-xs text-[#525252] font-body">
            We only read your public folder structure. No sign-in required.
          </p>
        </div>
      </div>
    </div>
  );
};

const SlideshowPage = () => {
  const navigate = useNavigate();
  const [folderData, setFolderData] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [imageError, setImageError] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    const storedData = localStorage.getItem('folder_data');
    if (!storedData) {
      navigate('/');
      return;
    }
    setFolderData(JSON.parse(storedData));
  }, [navigate]);

  const getAllSlideItems = useCallback(() => {
    if (!folderData) return [];

    const items = [];

    // Add image slides with their parent folder name
    folderData.items.forEach(item => {
      if (item.type === 'image') {
        const folderPath = item.path.substring(0, item.path.lastIndexOf('/')) || folderData.folder_name;
        items.push({
          ...item,
          folderName: folderPath
        });
      }
    });

    // Add empty folders with fallback images
    folderData.items.forEach(item => {
      if (item.type === 'folder') {
        const hasImages = folderData.items.some(
          i => i.type === 'image' && i.path.startsWith(item.path + '/')
        );
        if (!hasImages) {
          items.push({
            ...item,
            folderName: item.path,
            isEmptyFolder: true
          });
        }
      }
    });

    return items;
  }, [folderData]);

  const allItems = getAllSlideItems();

  const handleNext = useCallback(() => {
    setCurrentIndex((prev) => (prev + 1) % allItems.length);
    setImageError(false);
  }, [allItems.length]);

  const handlePrevious = useCallback(() => {
    setCurrentIndex((prev) => (prev - 1 + allItems.length) % allItems.length);
    setImageError(false);
  }, [allItems.length]);

  // Auto-play
  useEffect(() => {
    if (isPlaying && allItems.length > 0) {
      intervalRef.current = setInterval(() => {
        handleNext();
      }, 5000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, handleNext, allItems.length]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowRight') handleNext();
      else if (e.key === 'ArrowLeft') handlePrevious();
      else if (e.key === ' ') {
        e.preventDefault();
        setIsPlaying(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleNext, handlePrevious]);

  const getImageUrl = (item) => {
    if (item?.isEmptyFolder) {
      return FALLBACK_IMAGES[currentIndex % FALLBACK_IMAGES.length];
    }
    return `${API}/drive/image/${item?.id}`;
  };

  const handleGoBack = () => {
    localStorage.removeItem('folder_data');
    navigate('/');
  };

  if (!folderData) {
    return (
      <div className="h-screen flex items-center justify-center bg-white">
        <Spinner className="w-8 h-8 animate-spin text-[#002FA7]" />
      </div>
    );
  }

  if (allItems.length === 0) {
    return (
      <div className="h-screen flex items-center justify-center bg-white" data-testid="empty-state">
        <div className="text-center space-y-4">
          <h2 className="font-heading text-2xl font-bold text-[#0A0A0A]">No images found</h2>
          <p className="text-[#525252] font-body">This folder doesn't contain any images.</p>
          <Button onClick={handleGoBack} className="bg-[#002FA7] text-white rounded-sm">
            Go Back
          </Button>
        </div>
      </div>
    );
  }

  const currentSlide = allItems[currentIndex];
  const progressPercent = ((currentIndex + 1) / allItems.length) * 100;

  return (
    <div className="h-screen flex overflow-hidden bg-white" data-testid="slideshow-page">
      {/* Sidebar */}
      <div className="w-72 border-r border-[#E5E5E5] flex flex-col h-full bg-white flex-shrink-0">
        {/* Header */}
        <div className="p-6 border-b border-[#E5E5E5]">
          <h2
            className="font-heading text-xl font-bold text-[#0A0A0A] tracking-tight truncate"
            data-testid="folder-title"
            title={folderData.folder_name}
          >
            {folderData.folder_name}
          </h2>
          <p className="text-xs text-[#525252] mt-1 font-body">
            {folderData.total_images} images / {folderData.total_folders} folders
          </p>
        </div>

        {/* Folder Tree */}
        <ScrollArea className="flex-1" data-testid="folder-tree">
          <div className="p-3 space-y-0.5">
            {allItems.map((item, index) => (
              <div
                key={`${item.id}-${index}`}
                data-testid={`folder-item-${index}`}
                onClick={() => {
                  setCurrentIndex(index);
                  setImageError(false);
                }}
                className={`px-3 py-2.5 rounded-sm cursor-pointer transition-all duration-200 ${
                  index === currentIndex
                    ? 'bg-[#F2F2F2] text-[#0A0A0A] font-medium'
                    : 'text-[#525252] hover:bg-[#F2F2F2]/50'
                }`}
              >
                <div className="flex items-center gap-2">
                  {item.type === 'folder' || item.isEmptyFolder ? (
                    <Folder className="w-4 h-4 flex-shrink-0 text-[#002FA7]" weight="fill" />
                  ) : (
                    <ImageIcon className="w-4 h-4 flex-shrink-0" weight="fill" />
                  )}
                  <span className="text-xs font-body truncate" title={item.folderName || item.name}>
                    {item.name}
                  </span>
                </div>
                {(item.folderName || item.parent_folder) && (
                  <p className="text-[10px] text-[#525252]/70 mt-0.5 ml-6 truncate">
                    {item.folderName || item.parent_folder}
                  </p>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>

        {/* Back Button */}
        <div className="p-4 border-t border-[#E5E5E5]">
          <Button
            data-testid="back-button"
            onClick={handleGoBack}
            variant="outline"
            className="w-full rounded-sm font-body text-sm"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            New Folder
          </Button>
        </div>
      </div>

      {/* Main Slideshow Area */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Progress Bar */}
        <div className="h-1 bg-[#E5E5E5] w-full flex-shrink-0">
          <div
            className="h-full bg-[#002FA7] progress-bar"
            style={{ width: `${progressPercent}%` }}
            data-testid="progress-bar"
          ></div>
        </div>

        {/* Image Container - takes all remaining space */}
        <div className="flex-1 relative bg-[#0A0A0A] min-h-0" data-testid="slideshow-container">
          {currentSlide && (
            <>
              {!imageError ? (
                <img
                  key={currentSlide.id + '-' + currentIndex}
                  src={getImageUrl(currentSlide)}
                  alt={currentSlide.folderName || currentSlide.name}
                  className="absolute inset-0 w-full h-full object-contain slide-image bg-[#0A0A0A]"
                  data-testid="slideshow-image"
                  onError={() => setImageError(true)}
                />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center bg-[#F2F2F2]">
                  <ImageIcon className="w-16 h-16 text-[#E5E5E5]" />
                </div>
              )}
            </>
          )}
        </div>

        {/* Bottom Bar: Folder Name + Controls (outside the image) */}
        <div className="flex-shrink-0 bg-[#0A0A0A] border-t border-[#222] flex items-center justify-between px-4 py-2" data-testid="slideshow-controls">
          {/* Folder Name */}
          <div className="flex-1 min-w-0 mr-4">
            <p
              className="font-body font-medium text-white truncate"
              data-testid="folder-name-overlay"
              style={{ fontSize: '14px' }}
            >
              {currentSlide?.folderName || currentSlide?.parent_folder || currentSlide?.name || ''}
            </p>
            {currentSlide?.type === 'image' && (
              <p className="font-body text-white/50 truncate" style={{ fontSize: '12px' }}>
                {currentSlide.name}
              </p>
            )}
          </div>

          {/* Navigation Controls */}
          <div className="flex items-center gap-3 flex-shrink-0">
            <Button
              data-testid="previous-button"
              onClick={handlePrevious}
              variant="ghost"
              size="icon"
              className="rounded-sm hover:bg-white/10 h-8 w-8 text-white"
            >
              <CaretLeft className="w-5 h-5" weight="bold" />
            </Button>

            <Button
              data-testid="play-pause-button"
              onClick={() => setIsPlaying(!isPlaying)}
              variant="ghost"
              size="icon"
              className="rounded-sm hover:bg-white/10 h-8 w-8 text-white"
            >
              {isPlaying ? (
                <Pause className="w-5 h-5" weight="fill" />
              ) : (
                <Play className="w-5 h-5" weight="fill" />
              )}
            </Button>

            <Button
              data-testid="next-button"
              onClick={handleNext}
              variant="ghost"
              size="icon"
              className="rounded-sm hover:bg-white/10 h-8 w-8 text-white"
            >
              <CaretRight className="w-5 h-5" weight="bold" />
            </Button>

            <div className="h-4 w-px bg-white/20"></div>

            <div className="text-xs font-body text-white/70 font-medium tabular-nums" data-testid="slide-counter">
              {currentIndex + 1} / {allItems.length}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/slideshow" element={<SlideshowPage />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
