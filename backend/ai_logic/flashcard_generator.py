"""
Flashcard Generator with Gemini Vision API
Extracts text from images and PDFs, generates intelligent flashcards
"""

from google.generativeai import GenerativeModel, configure
import os
from typing import List, Dict, Optional
import base64

class FlashcardGenerator:
    def __init__(self):
        """Initialize Gemini Vision API with proper model verification"""
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        # Configure Gemini API
        configure(api_key=api_key)
        
        # Use gemini-2.5-flash - newest stable Flash model with vision support
        model_name = 'gemini-2.5-flash'
        self.model = GenerativeModel(model_name)
        print(f"✓ Flashcard Generator initialized with {model_name}")
    
    def _detect_mime_type(self, file_path: str) -> str:
        """
        Dynamically detect MIME type from file extension
        
        Args:
            file_path: Path to the file
            
        Returns:
            MIME type string
        """
        extension = os.path.splitext(file_path)[1].lower()
        mime_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.heic': 'image/heic',
            '.heif': 'image/heif',
            '.pdf': 'application/pdf'
        }
        return mime_type_map.get(extension, 'image/jpeg')
    
    def extract_text_from_pdf(self, pdf_path: str) -> Optional[str]:
        """
        Extract text from PDF using Gemini Vision API with robust error handling
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Extracted text from the PDF, or None if extraction fails
        """
        try:
            print(f"Extracting text from {os.path.basename(pdf_path)}...")
            
            # Read PDF file
            with open(pdf_path, 'rb') as pdf_file:
                pdf_data = pdf_file.read()
            
            # Verify file is not empty
            if not pdf_data:
                print("⚠️ PDF file is empty")
                return None
            
            # Create prompt for text extraction
            prompt = """Extract all readable text from this PDF document clearly and accurately.
This appears to be study notes or educational material.
Please extract the text exactly as it appears, maintaining structure and formatting where possible.
Include all headings, bullet points, definitions, formulas, and important concepts.
If there are multiple pages, extract content from all pages."""
            
            # Use Gemini Vision to extract text from PDF
            response = self.model.generate_content([
                prompt, 
                {"mime_type": "application/pdf", "data": pdf_data}
            ])
            
            if response and response.text:
                print(f"✓ Successfully extracted {len(response.text)} characters from PDF")
                return response.text
            else:
                print("⚠️ Gemini returned empty response for PDF")
                return None
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error extracting text from PDF: {error_msg}")
            
            # Provide helpful error messages
            if "404" in error_msg or "not found" in error_msg:
                print("   → Model not available. Check Gemini API documentation.")
            elif "429" in error_msg or "quota" in error_msg.lower():
                print("   → Rate limit exceeded. Please wait and try again.")
            elif "400" in error_msg:
                print("   → Invalid request. The PDF might be corrupted or too large.")
            
            return None
    
    def extract_text_from_image(self, image_path: str) -> Optional[str]:
        """
        Extract text from image using Gemini Vision API with robust error handling
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Extracted text from the image, or None if extraction fails
        """
        try:
            print(f"Extracting text from {os.path.basename(image_path)}...")
            
            # Read image file
            with open(image_path, 'rb') as img_file:
                image_data = img_file.read()
            
            # Verify file is not empty
            if not image_data:
                print("⚠️ Image file is empty")
                return None
            
            # Dynamically detect MIME type
            mime_type = self._detect_mime_type(image_path)
            print(f"   Detected MIME type: {mime_type}")
            
            # Create prompt for text extraction
            prompt = """Extract all readable text from this image clearly and accurately.
This appears to be study notes, a timetable, or educational material.
Please extract the text exactly as it appears, maintaining structure and formatting where possible.
Include all headings, bullet points, definitions, formulas, and important concepts."""
            
            # Use Gemini Vision to extract text
            response = self.model.generate_content([
                prompt, 
                {"mime_type": mime_type, "data": image_data}
            ])
            
            if response and response.text:
                print(f"✓ Successfully extracted {len(response.text)} characters from image")
                return response.text
            else:
                print("⚠️ Gemini returned empty response for image")
                return None
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error extracting text from image: {error_msg}")
            
            # Provide helpful error messages
            if "404" in error_msg or "not found" in error_msg:
                print("   → Model not available. Check Gemini API documentation.")
            elif "429" in error_msg or "quota" in error_msg.lower():
                print("   → Rate limit exceeded. Please wait and try again.")
            elif "400" in error_msg:
                print("   → Invalid request. The image might be corrupted or in an unsupported format.")
            
            return None
    
    def extract_text_from_file(self, file_path: str) -> Optional[str]:
        """
        Extract text from file with automatic format detection and fallback logic
        
        Args:
            file_path: Path to the file (PDF or image)
            
        Returns:
            Extracted text, or friendly error message if extraction fails
        """
        if not os.path.exists(file_path):
            return "❌ File not found. Please check the file path."
        
        extension = os.path.splitext(file_path)[1].lower()
        
        # Route to appropriate extraction method
        if extension == '.pdf':
            text = self.extract_text_from_pdf(file_path)
        elif extension in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif']:
            text = self.extract_text_from_image(file_path)
        else:
            return f"❌ Unsupported file format: {extension}"
        
        # Fallback message if extraction failed
        if text is None:
            return "⚠️ Gemini Vision could not read this file. Please try:\n• A clearer photo with better lighting\n• A higher resolution image\n• Converting handwritten notes to typed text\n• A different file format"
        
        # Return successfully extracted text
        return text
    
    def generate_flashcards(self, notes_text: str, topic: str = None, count: int = 10) -> List[Dict[str, str]]:
        """
        Generate flashcards from notes text using Gemini AI
        
        Args:
            notes_text: The extracted or provided notes text
            topic: Optional topic name for context
            count: Number of flashcards to generate
            
        Returns:
            List of flashcard dictionaries with 'question' and 'answer' keys
        """
        try:
            topic_context = f" on the topic '{topic}'" if topic else ""
            
            prompt = f"""
            Generate {count} intelligent flashcards{topic_context} based on the following notes.
            
            Create questions that:
            1. Test understanding of key concepts
            2. Are clear and concise
            3. Cover different aspects of the material
            4. Range from basic recall to application questions
            5. Include definitions, explanations, and examples where relevant
            
            Format your response as a JSON array with objects containing 'question' and 'answer' fields.
            Make answers detailed but concise (2-4 sentences).
            
            NOTES:
            {notes_text}
            
            Return ONLY the JSON array, no additional text.
            Example format:
            [
                {{"question": "What is...", "answer": "It is..."}},
                {{"question": "How does...", "answer": "It works by..."}}
            ]
            """
            
            response = self.model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if result_text.startswith('```'):
                result_text = result_text.split('\n', 1)[1]
                result_text = result_text.rsplit('```', 1)[0]
            
            # Parse JSON response
            import json
            flashcards = json.loads(result_text)
            
            return flashcards
            
        except Exception as e:
            print(f"Error generating flashcards: {e}")
            return []
    
    def generate_quiz(self, flashcards: List[Dict[str, str]], count: int = 5) -> List[Dict]:
        """
        Generate a quiz from flashcards with multiple choice options
        
        Args:
            flashcards: List of flashcard dictionaries
            count: Number of questions for the quiz
            
        Returns:
            List of quiz questions with multiple choice options
        """
        try:
            import random
            import json
            
            # Randomly select flashcards for quiz
            selected_cards = random.sample(flashcards, min(count, len(flashcards)))
            
            quiz_questions = []
            
            for card in selected_cards:
                prompt = f"""
                Create a multiple-choice quiz question based on this flashcard:
                Question: {card['question']}
                Correct Answer: {card['answer']}
                
                Generate 3 plausible but incorrect options along with the correct answer.
                Format your response as JSON:
                {{
                    "question": "the question text",
                    "options": ["option A", "option B", "option C", "option D"],
                    "correct_index": 0,
                    "explanation": "brief explanation of the correct answer"
                }}
                
                Return ONLY the JSON object.
                """
                
                response = self.model.generate_content(prompt)
                result_text = response.text.strip()
                
                # Remove markdown code blocks if present
                if result_text.startswith('```'):
                    result_text = result_text.split('\n', 1)[1]
                    result_text = result_text.rsplit('```', 1)[0]
                
                quiz_q = json.loads(result_text)
                quiz_questions.append(quiz_q)
            
            return quiz_questions
            
        except Exception as e:
            print(f"Error generating quiz: {e}")
            return []
    
    def generate_flashcards_from_image(self, image_path: str, topic: str = None, count: int = 10) -> List[Dict[str, str]]:
        """
        Complete pipeline: extract text from image and generate flashcards
        
        Args:
            image_path: Path to the notes image
            topic: Optional topic name
            count: Number of flashcards to generate
            
        Returns:
            List of flashcard dictionaries
        """
        # Extract text from image
        notes_text = self.extract_text_from_image(image_path)
        
        if not notes_text:
            return []
        
        # Generate flashcards from extracted text
        flashcards = self.generate_flashcards(notes_text, topic, count)
        
        return flashcards
