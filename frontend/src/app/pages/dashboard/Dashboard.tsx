import { useState, useEffect, useRef, useMemo, lazy, Suspense, useCallback } from 'react';
import { APP, KEY } from '../../../store/Store';
import styled, { useTheme } from 'styled-components';

import { Fade } from '../../../theme/styles/Effects';
import Pagination from '../../components/Pagination';

// Lazy load components
const Classic = lazy(() => import('./classic/Classic'));
const Race = lazy(() => import('./race/Race'));
const Charts = lazy(() => import('./charts/Charts'));

const DashBoard = styled.div`
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  overflow: hidden;
`;

const Wrapper = styled.div`
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
`;

const PageWrapper = styled.div.attrs(props => ({
  style: {
    transform: `translate3d(${props.translateX}, 0, 0)`,
    opacity: props.opacity,
    transition: props.isTransitioning 
      ? 'transform 0.4s ease-out, opacity 0.4s ease-out'
      : props.isDragging 
        ? 'none' 
        : 'transform 0.3s ease-out, opacity 0.3s ease-out'
  }
}))`
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  will-change: transform, opacity;
`;

const LoadingWrapper = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
`;

const DRAG_THRESHOLD = 30; // Reduced threshold for more responsive transitions
const TRANSITION_DURATION = 400;

function Dashboard() {
  const app = APP((state) => state);
  const key = KEY((state) => state);
  const theme = useTheme();
  const dashBoardRef = useRef(null);
  const resizeDebounceTimeout = useRef(null);

  const components = useMemo(() => [
    { name: "Classic", component: Classic },
    { name: "Race", component: Race },
    { name: "Charts", component: Charts },
  ], []);

  const defaultComponentIndex = useMemo(() => 
    components.findIndex(
      (item) => item.name === app.settings.general.defaultDash.value
    ), [components, app.settings.general.defaultDash.value]
  );

  // State management
  const [currentPageIndex, setCurrentPageIndex] = useState(defaultComponentIndex);
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [transitionState, setTransitionState] = useState({
    oldIndex: null,
    newIndex: null,
    direction: null
  });
  
  // Drag state
  const [dragStart, setDragStart] = useState(0);
  const [dragCurrent, setDragCurrent] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [isPointerDown, setIsPointerDown] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);

  const [windowSize, setWindowSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });

  // Utility functions
  const getAdjacentIndices = useCallback((index) => {
    const prevIndex = index === 0 ? components.length - 1 : index - 1;
    const nextIndex = index === components.length - 1 ? 0 : index + 1;
    return { prevIndex, nextIndex };
  }, [components.length]);

  // Cache container width to avoid repeated DOM queries
  const [containerWidth, setContainerWidth] = useState(window.innerWidth);

  const calculateDragPercentage = useCallback((dragDistance) => {
    return Math.max(-100, Math.min(100, (dragDistance / containerWidth) * 100));
  }, [containerWidth]);

  const resetDragState = useCallback(() => {
    setIsDragging(false);
    setIsPointerDown(false);
    setDragStart(0);
    setDragCurrent(0);
  }, []);

  // Window resize handler with container width caching
  useEffect(() => {
    const handleResize = () => {
      if (resizeDebounceTimeout.current) {
        clearTimeout(resizeDebounceTimeout.current);
      }
      resizeDebounceTimeout.current = setTimeout(() => {
        const newWidth = window.innerWidth;
        const newHeight = window.innerHeight;
        
        setWindowSize({
          width: newWidth,
          height: newHeight,
        });
        
        // Cache container width to avoid future DOM queries
        if (dashBoardRef.current) {
          setContainerWidth(dashBoardRef.current.offsetWidth || newWidth);
        } else {
          setContainerWidth(newWidth);
        }
      }, 100);
    };

    window.addEventListener('resize', handleResize);
    
    // Initial container width setup
    if (dashBoardRef.current) {
      setContainerWidth(dashBoardRef.current.offsetWidth || window.innerWidth);
    }
    
    return () => {
      clearTimeout(resizeDebounceTimeout.current);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  // Update content size (throttled to avoid frequent reflows)
  useEffect(() => {
    if (dashBoardRef.current) {
      const rect = dashBoardRef.current.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        // Update cached container width
        setContainerWidth(rect.width);
        
        app.update((state) => {
          if (state.system.interface) {
            state.system.contentSize.width = rect.width;
            state.system.contentSize.height = rect.height;
          }
        });
      }
    }
  }, [windowSize, app]);

  // Transition logic
  const performTransition = useCallback((direction) => {
    if (isTransitioning) return;

    const newIndex = direction === 'left' 
      ? (currentPageIndex === components.length - 1 ? 0 : currentPageIndex + 1)
      : (currentPageIndex === 0 ? components.length - 1 : currentPageIndex - 1);

    setIsTransitioning(true);
    setDragOffset(0);
    setTransitionState({
      oldIndex: currentPageIndex,
      newIndex: newIndex,
      direction: direction
    });

    setTimeout(() => {
      setCurrentPageIndex(newIndex);
      setIsTransitioning(false);
      setTransitionState({
        oldIndex: null,
        newIndex: null,
        direction: null
      });
    }, TRANSITION_DURATION);
  }, [isTransitioning, currentPageIndex, components.length]);

  const swipeLeft = useCallback(() => performTransition('left'), [performTransition]);
  const swipeRight = useCallback(() => performTransition('right'), [performTransition]);

  // Unified pointer handling
  const handlePointerStart = useCallback((position) => {
    if (isTransitioning) return;
    setIsPointerDown(true);
    setDragStart(position);
    setDragCurrent(position);
    setIsDragging(false);
    setDragOffset(0);
  }, [isTransitioning]);

  // Optimized pointer move handler with RAF throttling
  const handlePointerMove = useCallback((position) => {
    if (isTransitioning || !isPointerDown) return;
    
    // Use requestAnimationFrame to throttle updates
    requestAnimationFrame(() => {
      const dragDistance = position - dragStart;
      
      if (!isDragging && Math.abs(dragDistance) > 10) {
        setIsDragging(true);
      }

      if (isDragging || Math.abs(dragDistance) > 10) {
        setDragCurrent(position);
        const dragPercentage = calculateDragPercentage(dragDistance);
        setDragOffset(dragPercentage);
      }
    });
  }, [isTransitioning, isPointerDown, isDragging, dragStart, calculateDragPercentage]);

  const handlePointerEnd = useCallback(() => {
    if (isTransitioning || !isPointerDown) return;
    
    const dragDistance = dragCurrent - dragStart;
    const dragPercentage = calculateDragPercentage(dragDistance);
    
    if (Math.abs(dragPercentage) > DRAG_THRESHOLD) {
      if (dragPercentage > 0) {
        swipeRight();
      } else {
        swipeLeft();
      }
    } else {
      setDragOffset(0);
      setTimeout(() => setDragOffset(0), 50);
    }

    resetDragState();
  }, [isTransitioning, isPointerDown, dragCurrent, dragStart, calculateDragPercentage, swipeRight, swipeLeft, resetDragState]);

  // Event handlers
  const handleDoubleClick = useCallback((event) => {
    const clickX = event.clientX;
    const halfWindowWidth = window.innerWidth / 2;
    clickX < halfWindowWidth ? swipeRight() : swipeLeft();
  }, [swipeRight, swipeLeft]);

  // Global pointer up listener
  useEffect(() => {
    const handleGlobalPointerUp = () => {
      if (isPointerDown) {
        handlePointerEnd();
      }
    };

    document.addEventListener('mouseup', handleGlobalPointerUp);
    document.addEventListener('touchend', handleGlobalPointerUp);
    return () => {
      document.removeEventListener('mouseup', handleGlobalPointerUp);
      document.removeEventListener('touchend', handleGlobalPointerUp);
    };
  }, [isPointerDown, handlePointerEnd]);

  // Keyboard navigation
  useEffect(() => {
    if (key.keyStroke === app.settings.app_bindings.left.value) swipeRight();
    if (key.keyStroke === app.settings.app_bindings.right.value) swipeLeft();
  }, [key.keyStroke, app.settings.app_bindings.left.value, app.settings.app_bindings.right.value, swipeRight, swipeLeft]);

  // Get transform and opacity for each component
  const getComponentTransform = useCallback((index) => {
    const { prevIndex, nextIndex } = getAdjacentIndices(currentPageIndex);

    if (isDragging) {
      if (index === currentPageIndex) {
        return { translateX: `${dragOffset}%`, opacity: 1 - Math.abs(dragOffset) * 0.003 };
      }
      
      if (index === prevIndex && dragOffset > 0) {
        return { 
          translateX: `${dragOffset - 100}%`, 
          opacity: Math.max(0, dragOffset * 0.01) 
        };
      } else if (index === nextIndex && dragOffset < 0) {
        return { 
          translateX: `${dragOffset + 100}%`, 
          opacity: Math.max(0, Math.abs(dragOffset) * 0.01) 
        };
      }
      
      return { translateX: dragOffset > 0 ? '-100%' : '100%', opacity: 0 };
    }
    
    if (!isTransitioning) {
      if (index === currentPageIndex) {
        return { translateX: '0%', opacity: 1 };
      }
      return { translateX: '100%', opacity: 0 };
    }

    const { oldIndex, newIndex, direction } = transitionState;
    
    if (index === oldIndex) {
      return { 
        translateX: direction === 'left' ? '-100%' : '100%', 
        opacity: 0 
      };
    } else if (index === newIndex) {
      return { translateX: '0%', opacity: 1 };
    }
    
    return { translateX: '100%', opacity: 0 };
  }, [currentPageIndex, isDragging, dragOffset, isTransitioning, transitionState, getAdjacentIndices]);

  // Determine which components to render
  const shouldRender = useCallback((index) => {
    const { prevIndex, nextIndex } = getAdjacentIndices(currentPageIndex);

    if (isDragging) {
      return index === currentPageIndex || 
             (index === prevIndex && dragOffset > 0) || 
             (index === nextIndex && dragOffset < 0);
    }
    
    if (!isTransitioning) {
      return index === currentPageIndex;
    }
    
    const { oldIndex, newIndex } = transitionState;
    return index === oldIndex || index === newIndex;
  }, [currentPageIndex, isDragging, dragOffset, isTransitioning, transitionState, getAdjacentIndices]);

  return (
    <DashBoard
      ref={dashBoardRef}
      className={app.settings.general.colorTheme.value}
      onMouseDown={(e) => handlePointerStart(e.clientX)}
      onMouseMove={(e) => handlePointerMove(e.clientX)}
      onMouseUp={handlePointerEnd}
      onTouchStart={(e) => handlePointerStart(e.touches[0].clientX)}
      onTouchMove={(e) => handlePointerMove(e.touches[0].clientX)}
      onTouchEnd={handlePointerEnd}
      onDoubleClick={handleDoubleClick}
    >
      <Wrapper>
        {components.map(({ component: Component }, index) => {
          if (!shouldRender(index)) return null;

          const { translateX, opacity } = getComponentTransform(index);

          return (
            <PageWrapper 
              key={`page-${index}`}
              translateX={translateX}
              opacity={opacity}
              isTransitioning={isTransitioning}
              isDragging={isDragging}
            >
              <Suspense fallback={
                <LoadingWrapper>
                  <div>Loading...</div>
                </LoadingWrapper>
              }>
                <Component />
              </Suspense>
            </PageWrapper>
          );
        })}
      </Wrapper>
      <Pagination
        pages={components.length}
        colorActive={theme.colors.theme.blue.active}
        colorInactive={theme.colors.medium}
        currentPage={currentPageIndex}
        dotSize={7.5}
      />
    </DashBoard>
  );
}

export default Dashboard;