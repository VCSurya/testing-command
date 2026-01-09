self.onmessage = async (e) => {
    const { id, file, maxWidth, maxHeight, quality } = e.data;

    try {
        const bitmap = await createImageBitmap(file);

        let { width, height } = bitmap;
        const ratio = Math.min(maxWidth / width, maxHeight / height, 1);

        const canvas = new OffscreenCanvas(
            Math.round(width * ratio),
            Math.round(height * ratio)
        );
        const ctx = canvas.getContext("2d");
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);

        const blob = await canvas.convertToBlob({ type: "image/jpeg", quality });
        self.postMessage({ id, success: true, blob });
    } catch (err) {
        self.postMessage({ id, success: false, error: err.message });
    }
};
