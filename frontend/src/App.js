import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import '@/App.css';
import { 
  Play, 
  Pause, 
  CaretLeft, 
  CaretRight, 
  Folder, 
  Image as ImageIcon,
  GoogleLogo
} from '@phosphor-icons/react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
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
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const driveConnected = searchParams.get('drive_connected');
    const sessionId = searchParams.get('session_id');
    const error = searchParams.get('error');

    if (driveConnected === 'true' && sessionId) {
      localStorage.setItem('drive_session_id', sessionId);
      toast.success('Google Drive connected successfully!');
      navigate('/dashboard', { replace: true });
    }

    if (error === 'auth_failed') {
      toast.error('Authentication failed. Please try again.');
      navigate('/', { replace: true });
    }
  }, [searchParams, navigate]);

  const handleGoogleAuth = async () => {
    try {
      const response = await axios.get(`${API}/drive/connect`);
      window.location.href = response.data.authorization_url;
    } catch (error) {
      console.error('Auth error:', error);
      toast.error('Failed to initiate Google authentication');
    }
  };

  return (
    <div className="min-h-screen bg-white flex items-center justify-center p-6" data-testid="landing-page">
      <div className="max-w-2xl w-full space-y-8">
        {/* Header */}
        <div className="text-center space-y-4">
          <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl tracking-tighter font-black text-[#0A0A0A]" data-testid="landing-title">
            Drive Slideshow
          </h1>
          <p className="text-base leading-relaxed text-[#525252] max-w-xl mx-auto" data-testid="landing-subtitle">
            Transform your Google Drive folders into beautiful slideshows. View your images with folder names elegantly overlaid.
          </p>
        </div>

        {/* Main Card */}
        <div className="bg-[#F2F2F2] border border-[#E5E5E5] p-8 space-y-6">
          {/* Google Auth Section */}
          <div className="space-y-3">
            <label className="text-xs uppercase tracking-[0.2em] font-bold text-[#0A0A0A]" data-testid="auth-section-label">
              Connect Your Google Drive
            </label>
            <Button
              data-testid="google-auth-button"
              onClick={handleGoogleAuth}
              className="w-full bg-[#002FA7] text-white hover:bg-[#002FA7]/90 rounded-sm py-6 font-body flex items-center justify-center gap-3"
            >
              <GoogleLogo className="w-5 h-5" weight="bold" />
              <span className="font-medium">Sign in with Google</span>
            </Button>
            <p className="text-xs text-[#525252] font-body">
              Securely access your Drive folders with read-only permissions
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center">
          <p className="text-xs text-[#525252] font-body">
            Your privacy is protected. We only request read-only access to your Drive.
          </p>
        </div>
      </div>
    </div>
  );
};

const DashboardPage = () => {
  const navigate = useNavigate();
  const [driveLink, setDriveLink] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const storedSessionId = localStorage.getItem('drive_session_id');
    if (!storedSessionId) {
      navigate('/');
      return;
    }
    setSessionId(storedSessionId);
    checkDriveStatus(storedSessionId);
  }, [navigate]);

  const checkDriveStatus = async (sid) => {
    try {
      const response = await axios.get(`${API}/drive/status?session_id=${sid}`);
      setIsConnected(response.data.connected);
    } catch (error) {
      console.error('Status check error:', error);
      setIsConnected(false);
    }
  };

  const handleLoadFolder = async () => {
    if (!driveLink.trim()) {
      toast.error('Please enter a Google Drive folder link');
      return;
    }

    if (!sessionId) {
      toast.error('Session expired. Please sign in again.');
      navigate('/');
      return;
    }

    try {
      setLoading(true);
      const response = await axios.post(
        `${API}/drive/folder?session_id=${sessionId}`,
        { drive_link: driveLink }
      );

      localStorage.setItem('folder_data', JSON.stringify(response.data));
      navigate('/slideshow');
    } catch (error) {
      console.error('Folder fetch error:', error);
      toast.error(error.response?.data?.detail || 'Failed to access folder. Please check the link.');
    } finally {
      setLoading(false);
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('drive_session_id');
    localStorage.removeItem('folder_data');
    navigate('/');
    toast.success('Signed out successfully');
  };

  return (
    <div className="min-h-screen bg-white flex items-center justify-center p-6" data-testid="dashboard-page">
      <div className="max-w-2xl w-full space-y-8">
        {/* Header */}
        <div className="text-center space-y-4">
          <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl tracking-tighter font-black text-[#0A0A0A]" data-testid="dashboard-title">
            Select Folder
          </h1>
          <p className="text-base leading-relaxed text-[#525252] max-w-xl mx-auto">
            {isConnected ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                Connected to Google Drive
              </span>
            ) : (
              'Checking connection...'
            )}
          </p>
        </div>

        {/* Main Card */}
        <div className="bg-[#F2F2F2] border border-[#E5E5E5] p-8 space-y-6">
          {/* Folder Link Section */}
          <div className="space-y-3">
            <label className="text-xs uppercase tracking-[0.2em] font-bold text-[#0A0A0A]" data-testid="folder-link-label">
              Drive Folder Link
            </label>
            <div className="flex gap-2">
              <Input
                data-testid="drive-link-input"
                type="text"
                placeholder="https://drive.google.com/drive/folders/..."
                value={driveLink}
                onChange={(e) => setDriveLink(e.target.value)}
                className="flex-1 rounded-sm border-[#E5E5E5] focus:border-[#0A0A0A] focus:ring-1 focus:ring-[#0A0A0A] font-body"
                onKeyDown={(e) => e.key === 'Enter' && handleLoadFolder()}
              />
              <Button
                data-testid="load-folder-button"
                onClick={handleLoadFolder}
                disabled={loading}
                className="bg-[#002FA7] text-white hover:bg-[#002FA7]/90 rounded-sm px-6 font-body"
              >
                {loading ? 'Loading...' : 'Load'}
              </Button>
            </div>
            <p className="text-xs text-[#525252] font-body">
              Paste any Google Drive folder link from your account
            </p>
          </div>

          {/* Sign Out */}
          <div className="pt-4 border-t border-[#E5E5E5]">
            <Button
              data-testid="sign-out-button"
              onClick={handleSignOut}
              variant="outline"
              className="w-full rounded-sm font-body"
            >
              Sign Out
            </Button>
          </div>
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
  const [sessionId, setSessionId] = useState(null);

  useEffect(() => {
    const storedData = localStorage.getItem('folder_data');
    const storedSessionId = localStorage.getItem('drive_session_id');

    if (!storedData || !storedSessionId) {
      navigate('/');
      return;
    }

    setFolderData(JSON.parse(storedData));
    setSessionId(storedSessionId);
  }, [navigate]);

  // Auto-play effect
  useEffect(() => {
    if (!isPlaying || !folderData) return;

    const interval = setInterval(() => {
      handleNext();
    }, 5000);

    return () => clearInterval(interval);
  }, [isPlaying, currentIndex, folderData]);

  const handleNext = () => {
    if (!folderData) return;
    const allItems = getAllSlideItems();
    setCurrentIndex((prev) => (prev + 1) % allItems.length);
  };

  const handlePrevious = () => {
    if (!folderData) return;
    const allItems = getAllSlideItems();
    setCurrentIndex((prev) => (prev - 1 + allItems.length) % allItems.length);
  };

  const getAllSlideItems = () => {
    if (!folderData) return [];
    
    const items = [];
    const folders = {};

    // Group images by folder path
    folderData.items.forEach(item => {
      if (item.type === 'image') {
        const folderPath = item.path.substring(0, item.path.lastIndexOf('/')) || folderData.folder_name;
        if (!folders[folderPath]) {
          folders[folderPath] = [];
        }
        folders[folderPath].push(item);
      }
    });

    // Create slides: one per image
    folderData.items.forEach(item => {
      if (item.type === 'image') {
        const folderPath = item.path.substring(0, item.path.lastIndexOf('/')) || folderData.folder_name;
        items.push({
          ...item,
          folderName: folderPath
        });
      }
    });

    // Add folders without images
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
  };

  const getCurrentSlide = () => {
    const allItems = getAllSlideItems();
    return allItems[currentIndex];
  };

  const getImageUrl = (item) => {
    if (item?.isEmptyFolder) {
      return FALLBACK_IMAGES[Math.floor(Math.random() * FALLBACK_IMAGES.length)];
    }
    return `${API}/drive/image/${item?.id}?session_id=${sessionId}`;
  };

  const handleGoBack = () => {
    localStorage.removeItem('folder_data');
    navigate('/dashboard');
  };

  if (!folderData) {
    return (
      <div className="h-screen flex items-center justify-center bg-white">
        <div className="text-center space-y-2">
          <div className="text-2xl font-heading font-bold text-[#0A0A0A]">Loading...</div>
        </div>
      </div>
    );
  }

  const allItems = getAllSlideItems();
  const currentSlide = getCurrentSlide();
  const progressPercent = ((currentIndex + 1) / allItems.length) * 100;

  return (
    <div className="h-screen flex overflow-hidden bg-white" data-testid="slideshow-page">
      {/* Sidebar */}
      <div className="w-72 border-r border-[#E5E5E5] flex flex-col h-full bg-white">
        {/* Header */}
        <div className="p-6 border-b border-[#E5E5E5]">
          <h2 className="font-heading text-2xl font-bold text-[#0A0A0A] tracking-tight" data-testid="folder-title">
            {folderData.folder_name}
          </h2>
          <p className="text-xs text-[#525252] mt-1 font-body">
            {allItems.length} {allItems.length === 1 ? 'slide' : 'slides'}
          </p>
        </div>

        {/* Folder Tree */}
        <div className="flex-1 overflow-y-auto scrollbar-hide p-4" data-testid="folder-tree">
          <div className="space-y-1">
            {allItems.map((item, index) => (
              <div
                key={index}
                data-testid={`folder-item-${index}`}
                onClick={() => setCurrentIndex(index)}
                className={`p-3 rounded-sm cursor-pointer transition-smooth ${
                  index === currentIndex
                    ? 'bg-[#F2F2F2] text-[#0A0A0A]'
                    : 'text-[#525252] hover:bg-[#F2F2F2]/50'
                }`}
              >
                <div className="flex items-center gap-2">
                  {item.type === 'folder' || item.isEmptyFolder ? (
                    <Folder className="w-4 h-4 flex-shrink-0" weight="fill" />
                  ) : (
                    <ImageIcon className="w-4 h-4 flex-shrink-0" weight="fill" />
                  )}
                  <span className="text-sm font-body truncate">
                    {item.folderName || item.name}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Back Button */}
        <div className="p-4 border-t border-[#E5E5E5]">
          <Button
            data-testid="back-button"
            onClick={handleGoBack}
            variant="outline"
            className="w-full rounded-sm font-body"
          >
            ← Back
          </Button>
        </div>
      </div>

      {/* Main Slideshow Area */}
      <div className="flex-1 relative flex flex-col h-full overflow-hidden bg-[#F2F2F2]">
        {/* Progress Bar */}
        <div className="h-1 bg-[#E5E5E5] w-full">
          <div
            className="h-full bg-[#002FA7] progress-bar"
            style={{ width: `${progressPercent}%` }}
            data-testid="progress-bar"
          ></div>
        </div>

        {/* Image Container */}
        <div className="flex-1 relative slideshow-container" data-testid="slideshow-container">
          {currentSlide && (
            <>
              {/* Background Image */}
              <img
                src={getImageUrl(currentSlide)}
                alt={currentSlide.folderName || currentSlide.name}
                className="absolute inset-0 w-full h-full object-cover slide-image"
                data-testid="slideshow-image"
              />

              {/* Folder Name Overlay */}
              <div className="absolute inset-0 flex items-center justify-center p-8">
                <div className="bg-white/90 backdrop-blur-sm px-8 py-6 border border-[#E5E5E5]">
                  <h3
                    className="font-heading text-4xl sm:text-5xl lg:text-6xl tracking-tighter font-black text-[#0A0A0A] text-center"
                    data-testid="folder-name-overlay"
                  >
                    {currentSlide.folderName || currentSlide.name}
                  </h3>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Controls */}
        <div className="absolute bottom-8 left-1/2 -translate-x-1/2">
          <div className="bg-white/70 backdrop-blur-xl border border-[#E5E5E5] px-6 py-4 flex items-center gap-6" data-testid="slideshow-controls">
            <Button
              data-testid="previous-button"
              onClick={handlePrevious}
              variant="ghost"
              size="icon"
              className="rounded-sm hover:bg-[#F2F2F2]"
            >
              <CaretLeft className="w-6 h-6" weight="bold" />
            </Button>

            <Button
              data-testid="play-pause-button"
              onClick={() => setIsPlaying(!isPlaying)}
              variant="ghost"
              size="icon"
              className="rounded-sm hover:bg-[#F2F2F2]"
            >
              {isPlaying ? (
                <Pause className="w-6 h-6" weight="fill" />
              ) : (
                <Play className="w-6 h-6" weight="fill" />
              )}
            </Button>

            <Button
              data-testid="next-button"
              onClick={handleNext}
              variant="ghost"
              size="icon"
              className="rounded-sm hover:bg-[#F2F2F2]"
            >
              <CaretRight className="w-6 h-6" weight="bold" />
            </Button>

            <div className="ml-2 text-sm font-body text-[#0A0A0A] font-medium" data-testid="slide-counter">
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
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/slideshow" element={<SlideshowPage />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;