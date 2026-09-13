import { useEffect, useState } from 'react';
import { errorMessage, imageUrl, protectedResponse } from './api';

export function useInspectionImage(id: string | null) {
  const [image, setImage] = useState<{
    id: string | null;
    url: string | null;
    error: string | null;
  }>({ id: null, url: null, error: null });
  if (image.id !== id) setImage({ id, url: null, error: null });
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    let url: string | undefined;
    void (async () => {
      try {
        const response = await protectedResponse(imageUrl(id), { signal: controller.signal });
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        url = URL.createObjectURL(blob);
        setImage({ id, url, error: null });
      } catch (error) {
        if (!controller.signal.aborted) setImage({ id, url: null, error: errorMessage(error) });
      }
    })();
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [id]);
  return image.id === id ? image : { id, url: null, error: null };
}
