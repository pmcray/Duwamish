; ======================================================================
;  ELIZA, WITH THE DOCTOR SCRIPT -- after Joseph Weizenbaum (MIT, 1966)
;
;  ELIZA finds the most important keyword in what it is told, takes the
;  sentence apart with that keyword's decomposition patterns, and puts
;  the pieces back together with a reassembly rule, swapping "I" and
;  "you" as it goes.  Each decomposition's reassemblies are used in
;  turn.  A sentence is cut at a comma, a full stop or BUT: if a
;  keyword has been seen, what follows is dropped; if not, what went
;  before.  When the keyword is MY, ELIZA also remembers what was said,
;  and brings it up again when nothing else applies.
;
;  The script is a reconstruction of the part of DOCTOR that the
;  conversation printed in Weizenbaum's paper (CACM 9, 1966) needs; that
;  conversation follows.  In a pattern, 0 matches any words, a list
;  matches any one of its words, and a number in a reassembly stands
;  for that part of the decomposed sentence.
; ======================================================================

; what is said back to the patient: I and you exchanged
(define im (implode (explode "I'M")))
(define reflections
  (cons (list im 'YOU 'ARE)
        '((I YOU) (ME YOU) (MY YOUR) (YOUR MY) (YOU I) (AM ARE)
          (MYSELF YOURSELF) (YOURSELF MYSELF))))

(define family '(MOTHER FATHER SISTER BROTHER WIFE HUSBAND CHILDREN))
(define sad '(SAD UNHAPPY DEPRESSED SICK))
(define want '(WANT NEED))
(define be '(AM IS ARE WAS))

; the script: (keyword rank (pattern reassembly ...) ...)
(define script
  (list
   (list 'ALIKE 10 '((0) (IN WHAT WAY)))
   (list 'LIKE 10 (list (list 0 be 0 'LIKE 0) '(WHAT RESEMBLANCE DO YOU SEE)))
   (list 'ALWAYS 1 '((0) (CAN YOU THINK OF A SPECIFIC EXAMPLE)))
   (list 'MY 2
         (list (list 0 'YOUR 0 family 0)
               '(TELL ME MORE ABOUT YOUR FAMILY)
               '(WHO ELSE IN YOUR FAMILY 5)
               '(YOUR 4)
               '(WHAT ELSE COMES TO YOUR MIND WHEN YOU THINK OF YOUR 4))
         '((0 YOUR 0) (YOUR 3) (WHY DO YOU SAY YOUR 3)))
   (list 'I 0
         (list (list 0 'YOU want 0) '(WHAT WOULD IT MEAN TO YOU IF YOU GOT 4))
         (list (list 0 'YOU 'ARE 0 sad 0)
               '(I AM SORRY TO HEAR YOU ARE 5)
               '(DO YOU THINK COMING HERE WILL HELP YOU NOT TO BE 5))
         '((0) (YOU SAY 1)))
   (list 'YOU 0
         '((0 I ARE 0) (WHAT MAKES YOU THINK I AM 4)
                       (DOES IT PLEASE YOU TO BELIEVE I AM 4))
         '((0 I 0 YOU) (WHY DO YOU THINK I 3 YOU))
         '((0) (WE WERE DISCUSSING YOU NOT ME)))))

; I'M is a keyword that uses I's rules
(define synonyms (list (list im 'I)))

(define none '((I AM NOT SURE I UNDERSTAND YOU FULLY) (PLEASE GO ON)
               (WHAT DOES THAT SUGGEST TO YOU)))
(define memory nil)

; ----------------------------------------------------------------------
;  reading a sentence: characters into words; , . and BUT are marks
; ----------------------------------------------------------------------
(define comma (car (explode ",")))
(define stop (car (explode ".")))
(define (words chars word acc)
  (cond ((null chars)
         (reverse (if word (cons (implode (reverse word)) acc) acc)))
        ((eq (car chars) space)
         (words (cdr chars) nil (if word (cons (implode (reverse word)) acc) acc)))
        ((or (eq (car chars) comma) (eq (car chars) stop))
         (words (cdr chars) nil
                (cons 'MARK (if word (cons (implode (reverse word)) acc) acc))))
        (else (words (cdr chars) (cons (car chars) word) acc))))

(define (keyword w)
  (let ((s (assoc w synonyms)))
    (assoc (if s (cadr s) w) script)))

; cut at the marks: keep the clause with the first keyword
(define (clause ws seen acc)
  (cond ((null ws) (reverse acc))
        ((or (eq (car ws) 'MARK) (eq (car ws) 'BUT))
         (if seen (reverse acc) (clause (cdr ws) nil nil)))
        (else (clause (cdr ws) (or seen (keyword (car ws)))
                      (cons (car ws) acc)))))

(define (reflect ws)
  (cond ((null ws) nil)
        (else (let ((r (assoc (car ws) reflections)))
                (append (if r (cdr r) (list (car ws))) (reflect (cdr ws)))))))

; the best keyword: highest rank, the first if there is a tie
(define (best ws top)
  (cond ((null ws) top)
        (else (let ((k (keyword (car ws))))
                (best (cdr ws)
                      (if (and k (or (null top) (> (cadr k) (cadr top)))) k top))))))

; ----------------------------------------------------------------------
;  decomposition: match a pattern, giving the list of its parts
; ----------------------------------------------------------------------
(define (fits p w) (if (consp p) (member w p) (eq p w)))

(define (match pat ws)
  (cond ((null pat) (if (null ws) '(()) nil))
        ((eq (car pat) 0) (match0 (cdr pat) ws nil))
        ((null ws) nil)
        ((fits (car pat) (car ws))
         (let ((rest (match (cdr pat) (cdr ws))))
           (if rest (cons (list (car ws)) rest) nil)))
        (else nil)))

; 0 takes as few words as it can
(define (match0 pat ws taken)
  (let ((rest (match pat ws)))
    (cond (rest (cons (reverse taken) rest))
          ((null ws) nil)
          (else (match0 pat (cdr ws) (cons (car ws) taken))))))

(define (assemble tmpl parts)
  (cond ((null tmpl) nil)
        ((numberp (car tmpl)) (append (nth (car tmpl) parts)
                                      (assemble (cdr tmpl) parts)))
        (else (cons (car tmpl) (assemble (cdr tmpl) parts)))))

; use the decomposition's first reassembly, and move it to the back
(define (rotate rule)
  (let ((r (cadr rule)))
    (rplacd rule (append (cddr rule) (list r)))
    r))

(define (transform rules ws)
  (cond ((null rules) nil)
        (else (let ((parts (match (car (car rules)) ws)))
                (if parts (assemble (rotate (car rules)) parts)
                    (transform (cdr rules) ws))))))

(define (respond chars)
  (let ((ws (clause (words chars nil nil) nil nil)))
    (let ((k (best ws nil)) (rws (reflect ws)))
      (cond ((null k)
             (if memory
                 (let ((m (car memory))) (setq memory (cdr memory)) m)
                 (let ((r (car none))) (setq none (append (cdr none) (list r))) r)))
            (else
             (if (eq (car k) 'MY)
                 (let ((parts (match '(0 YOUR 0) rws)))
                   (if parts
                       (setq memory
                             (append memory
                                     (list (assemble '(DOES THAT HAVE ANYTHING TO DO
                                                       WITH THE FACT THAT YOUR 3)
                                                     parts))))
                       nil))
                 nil)
             (transform (cddr k) rws))))))

(define (patient text)
  (prin1 text) (terpri)
  (say (respond (explode text)))
  (terpri))

(say '(ELIZA WITH THE DOCTOR SCRIPT AFTER WEIZENBAUM 1966))
(terpri)

; the conversation in Weizenbaum's paper
(patient "MEN ARE ALL ALIKE.")
(patient "THEY'RE ALWAYS BUGGING US ABOUT SOMETHING OR OTHER.")
(patient "WELL, MY BOYFRIEND MADE ME COME HERE.")
(patient "HE SAYS I'M DEPRESSED MUCH OF THE TIME.")
(patient "IT'S TRUE. I AM UNHAPPY.")
(patient "I NEED SOME HELP, THAT MUCH SEEMS CERTAIN.")
(patient "PERHAPS I COULD LEARN TO GET ALONG WITH MY MOTHER.")
(patient "MY MOTHER TAKES CARE OF ME.")
(patient "MY FATHER.")
(patient "YOU ARE LIKE MY FATHER IN SOME WAYS.")
(patient "YOU ARE NOT VERY AGGRESSIVE BUT I THINK YOU DON'T WANT ME TO NOTICE THAT.")
(patient "YOU DON'T ARGUE WITH ME.")
(patient "YOU ARE AFRAID OF ME.")
(patient "MY FATHER IS AFRAID OF EVERYBODY.")
(patient "BULLIES.")
